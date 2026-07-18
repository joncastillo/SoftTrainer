"""Kyutai speech models for bidirectional voice conversation.

STT uses kyutai/stt-1b-en_fr and TTS uses the kyutai DSM TTS model,
both through the moshi package. Everything loads lazily on first use so
the rest of the app works without torch installed. The frontend falls
back to browser speech APIs when these report unavailable.
"""

import asyncio
import struct
import threading
from typing import Optional

import numpy as np

STT_REPO = "kyutai/stt-1b-en_fr"
SAMPLE_RATE = 24000

_lock = threading.Lock()
_stt = None
_tts = None


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
        self._mimi_ctx = self.mimi.streaming(1)
        self._lm_ctx = self.lm_gen.streaming(1)
        self._mimi_ctx.__enter__()
        self._lm_ctx.__enter__()

    def stop(self) -> None:
        for ctx in (self._lm_ctx, self._mimi_ctx):
            if ctx is not None:
                ctx.__exit__(None, None, None)
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
    """Return the shared STT instance, loading it on first call."""
    global _stt
    if not moshi_available():
        return None
    with _lock:
        if _stt is None:
            _stt = KyutaiSTT()
    return _stt


def get_tts() -> Optional[KyutaiTTS]:
    """Return the shared TTS instance, loading it on first call."""
    global _tts
    if not moshi_available():
        return None
    with _lock:
        if _tts is None:
            _tts = KyutaiTTS()
    return _tts


async def synthesize_async(text: str) -> Optional[bytes]:
    """Run TTS in a worker thread so the event loop stays responsive."""
    tts = get_tts()
    if tts is None:
        return None
    return await asyncio.get_running_loop().run_in_executor(None, tts.synthesize, text)


def speech_status() -> dict:
    return {
        "available": moshi_available(),
        "stt_loaded": _stt is not None,
        "tts_loaded": _tts is not None,
        "stt_model": STT_REPO,
        "sample_rate": SAMPLE_RATE,
    }
