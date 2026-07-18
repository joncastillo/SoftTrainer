"""SoftTrainer backend entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .llm.local_hf import transformers_available
from .routes import documents, models, providers, sessions
from .speech.kyutai import speech_status
from .vision.behavior import vision_available

app = FastAPI(title="SoftTrainer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
