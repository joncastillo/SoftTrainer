"""LLM provider configuration endpoints."""

from fastapi import APIRouter, HTTPException

from ..llm import registry
from ..schemas import ProviderConfig

router = APIRouter()


@router.get("/api/providers")
def list_providers() -> list[dict]:
    return registry.list_providers()


@router.post("/api/providers")
def upsert_provider(body: ProviderConfig) -> dict:
    registry.upsert_provider(body.model_dump())
    return {"ok": True}


@router.delete("/api/providers/{provider_id}")
def delete_provider(provider_id: str) -> dict:
    registry.delete_provider(provider_id)
    return {"ok": True}


@router.post("/api/providers/{provider_id}/activate")
def activate(provider_id: str) -> dict:
    registry.set_active(provider_id)
    return {"ok": True}


@router.post("/api/providers/{provider_id}/test")
async def test_provider(provider_id: str) -> dict:
    """Send a tiny prompt through the provider to verify it works."""
    try:
        provider = registry.get_provider(provider_id)
        reply = await provider.complete(
            [{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=10)
        return {"ok": True, "reply": reply.strip()}
    except Exception as e:
        raise HTTPException(502, f"Provider test failed: {e}")
