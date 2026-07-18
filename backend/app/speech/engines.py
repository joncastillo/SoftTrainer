"""Server TTS engine selection.

Kokoro 82M is preferred when installed: natural sounding, Apache
licensed and faster than realtime on a GPU (close to realtime on CPU).
Kyutai DSM TTS is the second choice. With neither usable the client
falls back to the browser voice. A model that fails to load (out of
memory, missing weights) is marked failed and skipped instead of
crashing the session.
"""

import asyncio
import logging
import threading
from typing import Optional

import numpy as np

from . import kyutai

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_engine = None
_engine_name: Optional[str] = None
_kokoro_failed = False


def kokoro_installed() -> bool:
    try:
        import kokoro  # noqa: F401
        return True
    except ImportError:
        return False


def tts_installed() -> bool:
    return (kokoro_installed() and not _kokoro_failed) or kyutai.usable()


def preferred_engine_name() -> Optional[str]:
    if kokoro_installed() and not _kokoro_failed:
        return "kokoro"
    if kyutai.usable():
        return "kyutai"
    return None


class KokoroTTS:
    """Kokoro 82M text to speech, 24 kHz output."""

    def __init__(self):
        from kokoro import KPipeline
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.pipeline = KPipeline(lang_code="a", device=device)
        except TypeError:
            self.pipeline = KPipeline(lang_code="a")

    def synthesize(self, text: str) -> Optional[bytes]:
        """Render text to a wav blob, or None for empty input."""
        text = text.strip()
        if not text:
            return None
        chunks = []
        for _, _, audio in self.pipeline(text, voice="af_heart"):
            chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return None
        return kyutai.float_to_wav(np.concatenate(chunks), 24000)


def get_tts():
    """Return the shared TTS engine, loading the best usable one on first call."""
    global _engine, _engine_name, _kokoro_failed
    with _lock:
        if _engine is not None:
            return _engine
        if kokoro_installed() and not _kokoro_failed:
            try:
                _engine = KokoroTTS()
                _engine_name = "kokoro"
                return _engine
            except Exception:
                logger.exception("Failed to load Kokoro TTS; trying the next engine")
                _kokoro_failed = True
    engine = kyutai.get_tts()
    if engine is not None:
        with _lock:
            _engine = engine
            _engine_name = "kyutai"
    return engine


async def synthesize_async(text: str) -> Optional[bytes]:
    """Run TTS in a worker thread, serialized since engines are stateful."""
    if not tts_installed():
        return None
    loop = asyncio.get_running_loop()

    def run() -> Optional[bytes]:
        engine = get_tts()
        if engine is None:
            return None
        with _lock:
            return engine.synthesize(text)

    return await loop.run_in_executor(None, run)


def speech_status() -> dict:
    return {
        "stt_available": kyutai.usable(),
        "tts_available": tts_installed(),
        "tts_engine": _engine_name or preferred_engine_name(),
        "stt_model": kyutai.STT_REPO,
        "sample_rate": kyutai.SAMPLE_RATE,
    }
