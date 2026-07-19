"""Bridge to a PersonaPlex full-duplex speech server.

PersonaPlex (NVIDIA's moshi fork) runs as a separate process in its own
venv and owns the whole conversation: it listens and speaks at the same
time, so barge-ins and overlaps are handled by the model itself instead
of our turn-taking heuristics. This module relays audio between the
browser session and that server: mic PCM is opus-encoded and streamed
up, the model's opus reply is decoded back to PCM for the client, and
the model's text stream is surfaced for subtitles and the transcript.

Wire protocol (binary WebSocket frames, first byte is the kind):
  0x00  handshake, sent by the server once ready
  0x01  opus audio bytes, both directions, 24 kHz mono
  0x02  utf8 text piece of the model's own speech, server to client
Persona and voice are query parameters on /api/chat: ``text_prompt``
(role description) and ``voice_prompt`` (a preset like ``NATF2.pt``).
"""

import asyncio
import logging
import os
from typing import Awaitable, Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
DEFAULT_URL = "ws://localhost:8998/api/chat"
DEFAULT_VOICE = "NATF2.pt"


def server_url() -> str:
    return os.environ.get("PERSONAPLEX_URL", DEFAULT_URL)


def deps_available() -> bool:
    """True when the opus codec and ws client this bridge needs exist."""
    try:
        import aiohttp  # noqa: F401
        import sphn  # noqa: F401
        return True
    except ImportError:
        return False


async def probe() -> bool:
    """Cheap reachability check so sessions can fall back to the cascade."""
    if not deps_available():
        return False
    import aiohttp
    base = server_url().replace("ws://", "http://").replace("wss://", "https://")
    base = base.rsplit("/api/", 1)[0] + "/"
    try:
        async with aiohttp.ClientSession() as http:
            # Any HTTP response at all means the server process is up; the
            # status code does not matter (the root route may 404 when the
            # bundled web UI is not being served).
            async with http.get(base, timeout=aiohttp.ClientTimeout(total=2)):
                return True
    except Exception:
        return False


class PersonaPlexBridge:
    """One live full-duplex conversation against the PersonaPlex server."""

    def __init__(
        self,
        text_prompt: str,
        voice_prompt: str,
        on_pcm: Callable[[np.ndarray], Awaitable[None]],
        on_text: Callable[[str], Awaitable[None]],
    ):
        self.text_prompt = text_prompt
        self.voice_prompt = voice_prompt or DEFAULT_VOICE
        self.on_pcm = on_pcm
        self.on_text = on_text
        self._http = None
        self._ws = None
        self._writer = None
        self._reader = None
        self._recv_task: Optional[asyncio.Task] = None
        self._pump_task: Optional[asyncio.Task] = None
        self._last_client_audio = 0.0
        self.closed = False

    async def connect(self, timeout: float = 15.0) -> None:
        import aiohttp
        import sphn

        self._writer = sphn.OpusStreamWriter(SAMPLE_RATE)
        self._reader = sphn.OpusStreamReader(SAMPLE_RATE)
        self._http = aiohttp.ClientSession()
        try:
            self._ws = await self._http.ws_connect(
                server_url(),
                params={"text_prompt": self.text_prompt,
                        "voice_prompt": self.voice_prompt},
                timeout=aiohttp.ClientWSTimeout(ws_close=timeout),
                max_msg_size=0,
            )
            # The server sends 0x00 once the model is ready for audio.
            msg = await asyncio.wait_for(self._ws.receive(), timeout)
            if msg.type != aiohttp.WSMsgType.BINARY or msg.data[:1] != b"\x00":
                raise RuntimeError(f"unexpected handshake from PersonaPlex: {msg}")
        except Exception:
            await self.close()
            raise
        self._recv_task = asyncio.create_task(self._recv_loop())
        self._pump_task = asyncio.create_task(self._silence_pump())

    async def send_pcm(self, pcm: np.ndarray) -> None:
        """Encode and ship float32 mono 24 kHz mic audio to the model.

        sphn >= 0.2 is push-style: append_pcm returns whatever opus bytes
        are ready (possibly empty while the encoder buffers a frame).
        """
        if self.closed or self._writer is None:
            return
        self._last_client_audio = asyncio.get_running_loop().time()
        data = self._writer.append_pcm(pcm.astype(np.float32))
        if data:
            await self._ws.send_bytes(b"\x01" + data)

    async def _silence_pump(self) -> None:
        """Keep the model stepping when the client mic is off.

        PersonaPlex is lock-step full duplex: it only generates output while
        consuming input frames. Without this, the trainer stays silent until
        the user enables their microphone. Send 80 ms of silence whenever no
        real mic audio has arrived recently.
        """
        frame = np.zeros(1920, dtype=np.float32)
        loop = asyncio.get_running_loop()
        try:
            while not self.closed:
                await asyncio.sleep(0.08)
                if loop.time() - self._last_client_audio > 0.24:
                    data = self._writer.append_pcm(frame)
                    if data:
                        await self._ws.send_bytes(b"\x01" + data)
        except Exception:
            if not self.closed:
                logger.exception("PersonaPlex silence pump failed")

    async def _recv_loop(self) -> None:
        import aiohttp
        try:
            async for msg in self._ws:
                if msg.type != aiohttp.WSMsgType.BINARY or not msg.data:
                    continue
                kind, payload = msg.data[0], msg.data[1:]
                if kind == 1:
                    pcm = self._reader.append_bytes(payload)
                    if pcm is not None and pcm.shape[-1] > 0:
                        await self.on_pcm(pcm)
                elif kind == 2:
                    await self.on_text(payload.decode("utf-8", errors="replace"))
        except Exception:
            if not self.closed:
                logger.exception("PersonaPlex receive loop failed")

    async def close(self) -> None:
        self.closed = True
        for task in (self._recv_task, self._pump_task):
            if task:
                task.cancel()
        self._recv_task = self._pump_task = None
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass
        try:
            if self._http is not None:
                await self._http.close()
        except Exception:
            pass
        self._ws = self._http = None
