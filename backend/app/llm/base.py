"""Common interface every chat provider implements."""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class ChatProvider(ABC):
    """Streams assistant text for a list of chat messages."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def stream_chat(self, messages: list[dict], max_tokens: int = 1024) -> AsyncIterator[str]:
        """Yield text deltas for the assistant reply."""
        ...

    async def complete(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """Convenience wrapper that collects the full reply."""
        parts = []
        async for delta in self.stream_chat(messages, max_tokens=max_tokens):
            parts.append(delta)
        return "".join(parts)
