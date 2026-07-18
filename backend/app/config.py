"""Application paths and settings, everything lives under a single data dir."""

import os
from pathlib import Path

BASE_DIR = Path(os.environ.get("SOFTTRAINER_DATA", Path(__file__).resolve().parents[2] / "data"))

SESSIONS_DIR = BASE_DIR / "sessions"
DOCUMENTS_DIR = BASE_DIR / "documents"
CONFIG_DIR = BASE_DIR / "config"
MODELS_DIR = BASE_DIR / "models"

for _d in (SESSIONS_DIR, DOCUMENTS_DIR, CONFIG_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

PROVIDERS_FILE = CONFIG_DIR / "providers.json"

DEFAULT_SESSION_MINUTES = 15
MAX_SESSION_MINUTES = 120
STT_SAMPLE_RATE = 24000
