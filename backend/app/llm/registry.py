"""Provider configuration store, persisted to disk as JSON."""

import json
from typing import Optional

from ..config import PROVIDERS_FILE
from .base import ChatProvider
from .local_hf import LocalHFProvider
from .providers import AnthropicProvider, OllamaProvider, OpenAICompatibleProvider

_KINDS = {
    "openai-compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
    "local-hf": LocalHFProvider,
}

_DEFAULTS = [
    {"id": "openai", "kind": "openai-compatible", "label": "OpenAI",
     "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
     "api_key_env": "OPENAI_API_KEY", "active": False},
    {"id": "anthropic", "kind": "anthropic", "label": "Anthropic",
     "base_url": "https://api.anthropic.com", "model": "claude-sonnet-5",
     "api_key_env": "ANTHROPIC_API_KEY", "active": False},
    {"id": "ollama", "kind": "ollama", "label": "Ollama (optional)",
     "base_url": "http://localhost:11434", "model": "llama3.2", "active": False},
    {"id": "local-hf", "kind": "local-hf", "label": "Self hosted model",
     "model": "", "active": True},
]


def _load() -> list[dict]:
    if PROVIDERS_FILE.exists():
        return json.loads(PROVIDERS_FILE.read_text(encoding="utf-8"))
    _save(_DEFAULTS)
    return json.loads(json.dumps(_DEFAULTS))


def _save(providers: list[dict]) -> None:
    PROVIDERS_FILE.write_text(json.dumps(providers, indent=2), encoding="utf-8")


def list_providers() -> list[dict]:
    """Return all provider configs with secrets masked."""
    out = []
    for p in _load():
        p = dict(p)
        if p.get("api_key"):
            p["api_key"] = "***"
        out.append(p)
    return out


def upsert_provider(config: dict) -> None:
    providers = _load()
    for i, p in enumerate(providers):
        if p["id"] == config["id"]:
            if config.get("api_key") == "***":
                config["api_key"] = p.get("api_key")
            providers[i] = config
            break
    else:
        providers.append(config)
    _save(providers)


def delete_provider(provider_id: str) -> None:
    _save([p for p in _load() if p["id"] != provider_id])


def set_active(provider_id: str) -> None:
    providers = _load()
    for p in providers:
        p["active"] = p["id"] == provider_id
    _save(providers)


def configure_local_model(repo_id: str) -> None:
    """Point the self hosted provider at a model and make it active."""
    providers = _load()
    entry = next((p for p in providers if p["kind"] == "local-hf"), None)
    if entry is None:
        entry = {"id": "local-hf", "kind": "local-hf",
                 "label": "Self hosted model", "model": repo_id}
        providers.append(entry)
    entry["model"] = repo_id
    for p in providers:
        p["active"] = p is entry
    _save(providers)


def get_provider(provider_id: Optional[str] = None) -> ChatProvider:
    """Build the requested provider, or the active one when id is None."""
    providers = _load()
    config = None
    if provider_id:
        config = next((p for p in providers if p["id"] == provider_id), None)
    if config is None:
        config = next((p for p in providers if p.get("active")), None)
    if config is None:
        raise RuntimeError("No LLM provider configured. Add one in Settings.")
    return _KINDS[config["kind"]](config)
