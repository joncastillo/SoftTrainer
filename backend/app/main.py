"""SoftTrainer backend entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .llm.local_hf import transformers_available
from .routes import documents, models, providers, sessions
from .speech.engines import speech_status
from .vision.behavior import vision_available

logger = logging.getLogger(__name__)

app = FastAPI(title="SoftTrainer", version="0.1.0")


@app.on_event("startup")
def _autoload_active_model() -> None:
    """Reload the active local model on boot so the first session works.

    The loaded model cache lives in process memory and is wiped on every
    restart. Without this the local provider raises "model not loaded"
    until someone reloads it by hand from the model manager, which is the
    usual cause of a session with no replies right after a restart.
    """
    try:
        from .hub import manager
        from .llm import registry

        active = next((p for p in registry.list_providers() if p.get("active")), None)
        if active and active.get("kind") == "local-hf" and active.get("model"):
            logger.info("Auto-loading active local model %s", active["model"])
            manager.start_load(active["model"])  # background thread, non blocking
    except Exception:
        logger.exception("Auto-load of active local model failed")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(documents.router)
app.include_router(providers.router)
app.include_router(models.router)


@app.get("/api/health")
def health() -> dict:
    """Report which optional capabilities are present on this install."""
    return {
        "ok": True,
        "speech": speech_status(),
        "vision": vision_available(),
        "local_llm": transformers_available(),
    }


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
