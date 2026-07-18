"""HTTP based providers: OpenAI compatible servers, Anthropic and Ollama.

The OpenAI compatible provider also covers vLLM, LM Studio, llama.cpp
server and most other self hosted gateways, since they all speak the
same chat completions protocol.
"""

import json
import os
from typing import AsyncIterator

import httpx

from .base import ChatProvider


def _resolve_key(config: dict) -> str:
    if config.get("api_key"):
        return config["api_key"]
    env = config.get("api_key_env")
    if env and os.environ.get(env):
        return os.environ[env]
    return ""


class OpenAICompatibleProvider(ChatProvider):
    """Talks to any /v1/chat/completions endpoint with SSE streaming."""

    async def stream_chat(self, messages: list[dict], max_tokens: int = 1024) -> AsyncIterator[str]:
        base = (self.config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        headers = {"Content-Type": "application/json"}
        key = _resolve_key(self.config)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{base}/chat/completions", json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta


class AnthropicProvider(ChatProvider):
    """Talks to the Anthropic Messages API with SSE streaming."""

    async def stream_chat(self, messages: list[dict], max_tokens: int = 1024) -> AsyncIterator[str]:
        base = (self.config.get("base_url") or "https://api.anthropic.com").rstrip("/")
        system = ""
        chat = []
        for m in messages:
            if m["role"] == "system":
                system += m["content"] + "\n"
            else:
                chat.append({"role": m["role"], "content": m["content"]})
        headers = {
            "x-api-key": _resolve_key(self.config),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config["model"],
            "max_tokens": max_tokens,
            "messages": chat,
            "stream": True,
        }
        if system.strip():
            payload["system"] = system.strip()
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{base}/v1/messages", json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {}).get("text")
                        if delta:
                            yield delta


class OllamaProvider(ChatProvider):
    """Talks to a local Ollama server."""

    async def stream_chat(self, messages: list[dict], max_tokens: int = 1024) -> AsyncIterator[str]:
        base = (self.config.get("base_url") or "http://localhost:11434").rstrip("/")
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{base}/api/chat", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content")
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        break
