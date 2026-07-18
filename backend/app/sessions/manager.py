"""Live session orchestration over one WebSocket connection.

Handles the turn loop: user speech or text comes in, the LLM answers as
the roleplay counterpart, the reply is streamed back as text and TTS
audio. The session is time bounded and ends with a generated report.
"""

import asyncio
import re
import time
from typing import Optional

from fastapi import WebSocket

from .. import storage
from ..llm.registry import get_provider
from ..rag import store as rag_store
from ..speech import kyutai
from ..vision.behavior import BehaviorAnalyzer
from .prompts import FORCE_END_NOTE, WRAPUP_NOTE, build_system_prompt
from .report import generate_report

WRAPUP_SECONDS = 120
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)


def strip_for_speech(text: str) -> str:
    """Remove code blocks and markdown noise so TTS speaks only prose."""
    text = CODE_BLOCK_RE.sub("", text)
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


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
        self.history: list[dict] = []
        self.started_at = time.time()
        self.deadline = self.started_at + meta.get("duration_minutes", 15) * 60
        self.wrapup_sent = False
        self.ended = False
        self.stt: Optional[kyutai.KyutaiSTT] = None
        self.partial = ""
        self._frame_count = 0

        chunks = [c["text"] for c in rag_store.search(
            meta["scenario"], meta.get("document_ids", []), top_k=4)]
        self.system_prompt = build_system_prompt(
            meta["scenario"], meta.get("difficulty", "medium"),
            meta.get("duration_minutes", 15), chunks)

    def seconds_left(self) -> float:
        return max(0.0, self.deadline - time.time())

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
            "speech": kyutai.speech_status(),
        })
        opener = (
            "System note: the session begins now. Greet the user in character "
            "and get the scenario started."
        )
        await self._assistant_turn(extra_note=opener)

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
        try:
            async for delta in self.provider.stream_chat(self._messages(note)):
                full += delta
                await self.send({"type": "assistant_delta", "text": delta})
        except Exception as e:
            await self.send({"type": "error", "message": f"LLM error: {e}"})
            return

        self.history.append({"role": "assistant", "content": full})
        storage.append_transcript(self.id, {"role": "assistant", "text": full})
        spoken = strip_for_speech(full)
        await self.send({
            "type": "assistant_message",
            "text": full,
            "spoken": spoken,
            "seconds_left": self.seconds_left(),
        })

        if spoken:
            wav = await kyutai.synthesize_async(spoken)
            if wav is not None:
                import base64
                await self.send({"type": "tts_audio", "wav_b64": base64.b64encode(wav).decode()})
            await self.send({"type": "tts_done"})

    async def handle_user_text(self, text: str) -> None:
        """Process a completed user utterance and produce the reply."""
        text = text.strip()
        if not text or self.ended:
            return
        self.history.append({"role": "user", "content": text})
        storage.append_transcript(self.id, {"role": "user", "text": text})
        await self.send({"type": "user_message", "text": text})

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
            self.partial += text
            await self.send({"type": "partial_transcript", "text": self.partial})

    async def commit_utterance(self) -> None:
        """Client detected end of speech, finalize the pending transcript."""
        text, self.partial = self.partial, ""
        if text.strip():
            await self.handle_user_text(text)

    async def handle_frame(self, jpeg_b64: str) -> None:
        """Analyze one webcam frame off the event loop."""
        if self.ended:
            return
        loop = asyncio.get_running_loop()
        sample = await loop.run_in_executor(None, self.behavior.analyze_frame, jpeg_b64)
        if sample is None:
            return
        self._frame_count += 1
        storage.append_metrics(self.id, sample)
        if self._frame_count % 4 == 0:
            await self.send({"type": "metrics", "sample": sample,
                             "rolling": self.behavior.summary()})

    async def end(self, reason: str) -> None:
        """Close the session, generate and send the final report."""
        if self.ended:
            return
        self.ended = True
        if self.stt is not None:
            self.stt.stop()
        summary = self.behavior.summary()
        storage.update_meta(self.id, status="generating_report", ended_at=time.time(),
                            end_reason=reason, behavior_summary=summary)
        await self.send({"type": "generating_report"})
        try:
            report = await generate_report(self.id, summary)
            await self.send({"type": "session_ended", "reason": reason, "report": report})
        except Exception as e:
            storage.update_meta(self.id, status="report_failed")
            await self.send({"type": "error", "message": f"Report generation failed: {e}"})
