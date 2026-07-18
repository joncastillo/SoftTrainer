"""Kyutai speech models for bidirectional voice conversation.

STT uses kyutai/stt-1b-en_fr and TTS uses the kyutai DSM TTS model,
both through the moshi package. Everything loads lazily on first use so
the rest of the app works without torch installed. The frontend falls
back to browser speech APIs when these report unavailable.
"""

import logging
import struct
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

STT_REPO = "kyutai/stt-1b-en_fr"
SAMPLE_RATE = 24000

_lock = threading.Lock()
_stt = None
_tts = None
# Set when constructing a model actually fails (e.g. out of memory, missing
# weights). Import succeeding is not enough to promise the models will load,
# so this gates the reported availability and drives the browser fallback.
_load_failed = False


def moshi_available() -> bool:
    try:
        import moshi  # noqa: F401
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def pcm16_to_float(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def float_to_wav(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode mono float audio as a 16 bit PCM wav blob."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16
    ) + b"data" + struct.pack("<I", len(pcm))
    return header + pcm


class KyutaiSTT:
    """Streaming speech to text over Mimi codec frames."""

    def __init__(self):
        import torch
        from moshi.models import LMGen, loaders

        # Defence in depth against a missing compiler: if torch.compile is
        # still reached, fall back to eager rather than aborting the session.
        try:
            torch._dynamo.config.suppress_errors = True
        except Exception:
            pass

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        info = loaders.CheckpointInfo.from_hf_repo(STT_REPO)
        self.mimi = info.get_mimi(device=self.device)
        self.tokenizer = info.get_text_tokenizer()
        lm = info.get_moshi(device=self.device)
        self.lm_gen = LMGen(lm, temp=0, temp_text=0, use_sampling=False)
        self.frame_size = int(self.mimi.sample_rate / self.mimi.frame_rate)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._mimi_ctx = None
        self._lm_ctx = None

    def start(self) -> None:
        # This instance is shared across sessions. A prior session that ended
        # without a clean stop (a dropped WebSocket) leaves the mimi and lm
        # modules mid stream, and moshi then asserts "already streaming" here,
        # which kills speech to text for every session until a restart. Reset
        # any leftover streaming state first so each session starts clean.
        self.stop()
        self._mimi_ctx = self.mimi.streaming(1)
        self._lm_ctx = self.lm_gen.streaming(1)
        self._mimi_ctx.__enter__()
        self._lm_ctx.__enter__()

    def stop(self) -> None:
        for ctx in (self._lm_ctx, self._mimi_ctx):
            if ctx is not None:
                try:
                    ctx.__exit__(None, None, None)
                except Exception:
                    logger.exception("Error resetting Kyutai STT streaming state")
        self._mimi_ctx = self._lm_ctx = None
        self._buffer = np.zeros(0, dtype=np.float32)

    def feed(self, audio: np.ndarray) -> str:
        """Feed float audio at 24 kHz, returns any newly decoded text."""
        torch = self.torch
        self._buffer = np.concatenate([self._buffer, audio])
        pieces = []
        while len(self._buffer) >= self.frame_size:
            frame = self._buffer[: self.frame_size]
            self._buffer = self._buffer[self.frame_size:]
            chunk = torch.from_numpy(frame)[None, None].to(self.device)
            with torch.no_grad():
                codes = self.mimi.encode(chunk)
                tokens = self.lm_gen.step(codes)
            if tokens is None:
                continue
            token = tokens[0, 0, 0].item()
            if token not in (0, 3):
                pieces.append(self.tokenizer.id_to_piece(token).replace("▁", " "))
        return "".join(pieces)


class KyutaiTTS:
    """Text to speech through the kyutai DSM TTS model."""

    def __init__(self):
        import torch
        from moshi.models.loaders import CheckpointInfo
        from moshi.models.tts import DEFAULT_DSM_TTS_REPO, TTSModel

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        info = CheckpointInfo.from_hf_repo(DEFAULT_DSM_TTS_REPO)
        self.model = TTSModel.from_checkpoint_info(
            info, n_q=32, temp=0.6, device=torch.device(self.device)
        )
        voice = "expresso/ex03-ex01_happy_001_channel1_334s.wav"
        voice_path = self.model.get_voice_path(voice)
        self.attributes = self.model.make_condition_attributes([voice_path], cfg_coef=2.0)

    def synthesize(self, text: str) -> Optional[bytes]:
        """Render text to a wav blob, or None for empty input."""
        text = text.strip()
        if not text:
            return None
        model = self.model
        entries = model.prepare_script([text], padding_between=1)
        pcms: list[np.ndarray] = []

        def on_frame(frame):
            if (frame != -1).all():
                pcm = model.mimi.decode(frame[:, 1:, :]).cpu().numpy()
                pcms.append(np.clip(pcm[0, 0], -1, 1))

        with self.torch.no_grad(), model.mimi.streaming(1):
            model.generate([entries], [self.attributes], on_frame=on_frame)
        if not pcms:
            return None
        audio = np.concatenate(pcms, axis=-1)
        return float_to_wav(audio, int(model.mimi.sample_rate))


def get_stt() -> Optional[KyutaiSTT]:
    """Return the shared STT instance, loading it on first call.

    Returns None (and flips the app to browser speech) if the model cannot
    be constructed, instead of letting the failure abort the session.
    """
    global _stt, _load_failed
    if not moshi_available() or _load_failed:
        return None
    with _lock:
        if _stt is None:
            try:
                _stt = KyutaiSTT()
            except Exception:
                logger.exception("Failed to load Kyutai STT model; falling back to browser speech")
                _load_failed = True
                return None
    return _stt


def get_tts() -> Optional[KyutaiTTS]:
    """Return the shared TTS instance, loading it on first call.

    Returns None on load failure so TTS degrades to browser speech synthesis
    rather than crashing the reply.
    """
    global _tts, _load_failed
    if not moshi_available() or _load_failed:
        return None
    with _lock:
        if _tts is None:
            try:
                _tts = KyutaiTTS()
            except Exception:
                logger.exception("Failed to load Kyutai TTS model; falling back to browser speech")
                _load_failed = True
                return None
    return _tts


def usable() -> bool:
    """True while the models are importable and have not failed to load."""
    return moshi_available() and not _load_failed
