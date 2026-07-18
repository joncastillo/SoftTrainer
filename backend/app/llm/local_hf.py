"""Local inference for Hugging Face models via transformers.

Models are downloaded through the hub manager into the app data dir and
loaded once, then reused across sessions. Generation runs in a worker
thread and streams tokens back to the async caller.
"""

import asyncio
import threading
from typing import AsyncIterator, Optional

from .base import ChatProvider

_loaded: dict[str, tuple] = {}
_lock = threading.Lock()


def transformers_available() -> bool:
    try:
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def load_model(repo_id: str, local_path: str) -> None:
    """Load a downloaded model into memory, cached by repo id."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    with _lock:
        if repo_id in _loaded:
            return
        tokenizer = AutoTokenizer.from_pretrained(local_path)
        model = AutoModelForCausalLM.from_pretrained(
            local_path,
            torch_dtype="auto",
            device_map="auto" if torch.cuda.is_available() else None,
        )
        _loaded[repo_id] = (tokenizer, model)


def unload_model(repo_id: str) -> None:
    with _lock:
        _loaded.pop(repo_id, None)


def loaded_models() -> list[str]:
    return list(_loaded.keys())


def get_loaded(repo_id: str) -> Optional[tuple]:
    return _loaded.get(repo_id)


class LocalHFProvider(ChatProvider):
    """Streams from a model previously loaded with load_model."""

    async def stream_chat(self, messages: list[dict], max_tokens: int = 1024) -> AsyncIterator[str]:
        from transformers import TextIteratorStreamer

        repo_id = self.config.get("model") or ""
        pair = get_loaded(repo_id)
        if pair is None:
            hint = "Open the model manager and load a model first."
            raise RuntimeError(
                f"Model {repo_id!r} is not loaded. {hint}" if repo_id else f"No model selected. {hint}"
            )
        tokenizer, model = pair
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

        thread = threading.Thread(
            target=model.generate,
            kwargs={**inputs, "max_new_tokens": max_tokens, "do_sample": True,
                    "temperature": 0.7, "streamer": streamer},
            daemon=True,
        )
        thread.start()

        loop = asyncio.get_running_loop()
        it = iter(streamer)
        while True:
            piece = await loop.run_in_executor(None, lambda: next(it, None))
            if piece is None:
                break
            if piece:
                yield piece
