"""Application paths and settings, everything lives under a single data dir."""

import os
from pathlib import Path

# The Kyutai/moshi speech models (and Kokoro) invoke torch.compile at
# inference time. On a machine without a C/C++ compiler this raises
# "Compiler: cl is not found" (no MSVC on Windows) and kills speech to text.
# Force eager execution so the models run without a compiler: a little
# slower, but functional. These must be set before torch compiles anything,
# and config is imported well before any inference runs.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

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
