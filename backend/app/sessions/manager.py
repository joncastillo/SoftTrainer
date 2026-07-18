"""Live session orchestration over one WebSocket connection.

Handles the turn loop: user speech or text comes in, the LLM answers as
the roleplay counterpart, the reply is streamed back as text and TTS
audio. The session is time bounded and ends with a generated report.
"""

import asyncio
import base64
import re
import time
from typing import Optional

from fastapi import WebSocket

from .. import storage
from ..llm.registry import get_provider
from ..rag import store as rag_store
from ..speech import engines, kyutai
from ..vision.behavior import BehaviorAnalyzer
from ..vision.coach import BehaviorCoach
from .delivery import DeliveryAnalyzer
from .keypoints import KeyPointTracker
from .pressure import PressureDirector
from .prompts import FORCE_END_NOTE, WRAPUP_NOTE, build_system_prompt
from .report import generate_report

WRAPUP_SECONDS = 120
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def strip_for_speech(text: str) -> str:
    """Remove code blocks and markdown noise so TTS speaks only prose."""
    text = CODE_BLOCK_RE.sub("", text)
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


class SpeechStreamer:
    """Speaks completed sentences while the LLM reply is still streaming.

    Prose is separated from code fences on the fly, split into sentences
    and fed to a single worker so audio chunks arrive in order with low
    latency instead of one big blob after the whole reply.
    """

    def __init__(self, session: "LiveSession"):
        self.session = session
        self.enabled = engines.tts_installed()
        self.raw = ""
        self.buf = ""
        self.in_code = False
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task = asyncio.create_task(self._worker()) if self.enabled else None

    async def _worker(self) -> None:
        while True:
            text = await self.queue.get()
            if text is None:
                return
            try:
                wav = await engines.synthesize_async(text)
            except Exception:
                continue
            if wav:
                await self.session.send(
                    {"type": "tts_audio", "wav_b64": base64.b64encode(wav).decode()})

    def _extract_prose(self, final: bool) -> str:
        """Pull prose out of raw text, skipping code fences.

        A short tail is held back on non final calls so a fence marker
        split across two deltas is not misread as prose.
        """
        out = []
        while True:
            idx = self.raw.find("```")
            if idx == -1:
                keep = 0 if final else 2
                cut = max(0, len(self.raw) - keep)
                if not self.in_code:
                    out.append(self.raw[:cut])
                self.raw = self.raw[cut:]
                return "".join(out)
            if not self.in_code:
                out.append(self.raw[:idx])
            self.raw = self.raw[idx + 3:]
            self.in_code = not self.in_code

    def _enqueue(self, text: str) -> None:
        text = re.sub(r"[*_#`>|]", "", text).strip()
        if text:
            self.queue.put_nowait(text)

    async def feed(self, delta: str) -> None:
        if not self.enabled:
            return
        self.raw += delta
        self.buf += self._extract_prose(final=False)
        parts = SENTENCE_SPLIT_RE.split(self.buf)
        for sentence in parts[:-1]:
            self._enqueue(sentence)
        self.buf = parts[-1]

    async def finish(self) -> None:
        """Flush remaining prose and wait for all audio to be sent."""
        if not self.enabled:
            await self.session.send({"type": "tts_done"})
            return
        self.buf += self._extract_prose(final=True)
        self._enqueue(self.buf)
        self.buf = ""
        self.queue.put_nowait(None)
        if self.task:
            await self.task
        await self.session.send({"type": "tts_done"})

    def cancel(self) -> None:
        if self.task:
            self.task.cancel()


class LiveSession:
    """State for one connected training session."""

    def __init__(self, session_id: str, ws: WebSocket):
        meta = storage.read_meta(session_id)
        if meta is None:
            raise ValueError(f"Unknown session {session_id}")
        self.id = session_id
        self.meta = meta
        self.ws = ws
        self.provider = get_provider(meta.get("provider_id"))
        self.behavior = BehaviorAnalyzer()
        self.coach = BehaviorCoach()
        self.delivery = DeliveryAnalyzer()
        self.keypoints = KeyPointTracker(meta.get("key_points") or [])
        self.pressure = PressureDirector(meta.get("pressure", "off"))
        self.history: list[dict] = []
        self.started_at = time.time()
        self.deadline = self.started_at + meta.get("duration_minutes", 15) * 60
        self.wrapup_sent = False
        self.ended = False
        self.stt: Optional[kyutai.KyutaiSTT] = None
        self.partial = ""
        self._utterance_started_at: Optional[float] = None
        # Browser-recognition clients report speech activity explicitly,
        # since their audio never reaches the server.
        self._client_speaking_since: Optional[float] = None
        self._frame_count = 0

        chunks = [c["text"] for c in rag_store.search(
            meta["scenario"], meta.get("document_ids", []), top_k=4)]
        self.system_prompt = build_system_prompt(
            meta["scenario"], meta.get("difficulty", "medium"),
            meta.get("duration_minutes", 15), chunks,
            pressure=self.pressure.enabled)

    def seconds_left(self) -> float:
        return max(0.0, self.deadline - time.time())

    def set_client_speaking(self, active: bool) -> None:
        """Speech-activity signal from clients using browser recognition."""
        if active:
            if self._client_speaking_since is None:
                self._client_speaking_since = time.time()
        else:
            self._client_speaking_since = None

    def user_speaking_seconds(self) -> float:
        """How long the user has been talking right now, 0 when silent."""
        since = self._utterance_started_at or self._client_speaking_since
        return time.time() - since if since else 0.0

    async def send(self, payload: dict) -> None:
        await self.ws.send_json(payload)

    async def start(self) -> None:
        """Kick off the session with the trainer speaking first."""
        storage.update_meta(self.id, status="active", started_at=self.started_at)
        stt = kyutai.get_stt()
        if stt is not None:
            self.stt = stt
            stt.start()
        await self.send({
            "type": "session_started",
            "seconds_left": self.seconds_left(),
            "speech": engines.speech_status(),
            "key_points": self.keypoints.points(),
        })
        opener = (
            "System note: the session begins now. Open in character with a warm, "
            "natural introduction as described in your instructions, then lead "
            "into your first question or opening move."
        )
        await self._assistant_turn(extra_note=opener)
        self.pressure.start(self)

    def _messages(self, extra_note: Optional[str] = None) -> list[dict]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.history)
        if extra_note:
            messages.append({"role": "system", "content": extra_note})
        return messages

    async def _assistant_turn(self, extra_note: Optional[str] = None) -> None:
        """Stream one LLM reply to the client, then speak it."""
        note = extra_note
        if not note and not self.wrapup_sent and self.seconds_left() < WRAPUP_SECONDS:
            note = WRAPUP_NOTE.format(seconds=int(self.seconds_left()))
            self.wrapup_sent = True

        full = ""
        speech = SpeechStreamer(self)
        try:
            async for delta in self.provider.stream_chat(self._messages(note)):
                full += delta
                await self.send({"type": "assistant_delta", "text": delta})
                await speech.feed(delta)
        except Exception as e:
            speech.cancel()
            await self.send({"type": "error", "message": f"LLM error: {e}"})
            return

        self.history.append({"role": "assistant", "content": full})
        storage.append_transcript(self.id, {"role": "assistant", "text": full})
        await self.send({
            "type": "assistant_message",
            "text": full,
            "spoken": strip_for_speech(full),
            "seconds_left": self.seconds_left(),
        })
        await speech.finish()

    async def handle_user_text(self, text: str, duration: Optional[float] = None) -> None:
        """Process a completed user utterance and produce the reply.

        ``duration`` is the spoken length in seconds when known (voice turns),
        used to estimate speaking pace; it is None for typed turns.
        """
        text = text.strip()
        if not text or self.ended:
            return
        self.history.append({"role": "user", "content": text})
        storage.append_transcript(self.id, {"role": "user", "text": text})
        await self.send({"type": "user_message", "text": text})

        elapsed = 1.0 - self.seconds_left() / max(1.0, self.deadline - self.started_at)
        changed, kp_tip = self.keypoints.observe(text, elapsed)
        if changed:
            await self.send({"type": "key_points", "points": self.keypoints.points()})
        # Always feed the delivery stats, but surface at most one tip per
        # turn; thread-loss recovery beats delivery nudges.
        delivery_tip = self.delivery.observe(text, duration)
        tip = kp_tip or delivery_tip
        if tip is not None:
            await self.send({"type": "coach_tip", **tip})

        if self.seconds_left() <= 0:
            await self._assistant_turn(extra_note=FORCE_END_NOTE)
            await self.end("time_up")
            return
        await self._assistant_turn()

    async def handle_audio(self, pcm16_b64: str) -> None:
        """Feed mic audio into streaming STT and emit partial transcripts."""
        if self.stt is None or self.ended:
            return
        import base64
        audio = kyutai.pcm16_to_float(base64.b64decode(pcm16_b64))
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, self.stt.feed, audio)
        if text:
            if self._utterance_started_at is None:
                self._utterance_started_at = time.time()
            self.partial += text
            await self.send({"type": "partial_transcript", "text": self.partial})

    async def commit_utterance(self) -> None:
        """Client detected end of speech, finalize the pending transcript."""
        text, self.partial = self.partial, ""
        started, self._utterance_started_at = self._utterance_started_at, None
        if text.strip():
            duration = (time.time() - started) if started else None
            await self.handle_user_text(text, duration)

    async def handle_frame(self, jpeg_b64: str) -> None:
        """Analyze one webcam frame off the event loop."""
        if self.ended:
            return
        loop = asyncio.get_running_loop()
        try:
            sample = await loop.run_in_executor(None, self.behavior.analyze_frame, jpeg_b64)
        except Exception:
            return
        if sample is None:
            return
        self._frame_count += 1
        storage.append_metrics(self.id, sample)
        if self._frame_count % 4 == 0:
            await self.send({"type": "metrics", "sample": sample,
                             "rolling": self.behavior.summary()})
            tip = self.coach.observe(self.behavior.samples)
            if tip is not None:
                await self.send({"type": "coach_tip", **tip})

    async def end(self, reason: str) -> None:
        """Close the session, generate and send the final report."""
        if self.ended:
            return
        self.ended = True
        self.pressure.stop()
        if self.stt is not None:
            self.stt.stop()
        summary = self.behavior.summary()
        delivery = self.delivery.summary()
        keypoints = self.keypoints.summary()
        composure = self.pressure.composure_summary(
            self.delivery.records, self.behavior.samples)
        storage.update_meta(self.id, status="generating_report", ended_at=time.time(),
                            end_reason=reason, behavior_summary=summary,
                            delivery_summary=delivery, keypoints_summary=keypoints,
                            composure_summary=composure)
        await self.send({"type": "generating_report"})
        try:
            report = await generate_report(self.id, summary, delivery, keypoints, composure)
            await self.send({"type": "session_ended", "reason": reason, "report": report})
        except Exception as e:
            storage.update_meta(self.id, status="report_failed")
            await self.send({"type": "error", "message": f"Report generation failed: {e}"})
