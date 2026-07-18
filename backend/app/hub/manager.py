"""Hugging Face hub integration: scan, download, load, self host models.

Downloads and loads run in background threads with pollable status so
the UI can show progress. Loading a model also points the local
provider at it and activates that provider, so the app hosts the model
itself with no external inference server.
"""

import shutil
import threading
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

from ..config import MODELS_DIR
from ..llm import local_hf, registry

RECOMMENDED = [
    {"repo_id": "Qwen/Qwen2.5-0.5B-Instruct", "params": "0.5B",
     "note": "Very fast, fine on CPU, good first model"},
    {"repo_id": "Qwen/Qwen2.5-1.5B-Instruct", "params": "1.5B",
     "note": "Good balance of speed and quality on CPU"},
    {"repo_id": "HuggingFaceTB/SmolLM2-1.7B-Instruct", "params": "1.7B",
     "note": "Small and fully open"},
    {"repo_id": "Qwen/Qwen2.5-3B-Instruct", "params": "3B",
     "note": "Strong quality, best with a GPU"},
    {"repo_id": "microsoft/Phi-3.5-mini-instruct", "params": "3.8B",
     "note": "Strong reasoning for its size"},
    {"repo_id": "meta-llama/Llama-3.2-1B-Instruct", "params": "1B", "gated": True,
     "note": "Needs the Llama license accepted on the hub"},
    {"repo_id": "meta-llama/Llama-3.2-3B-Instruct", "params": "3B", "gated": True,
     "note": "Needs the Llama license accepted on the hub"},
    {"repo_id": "google/gemma-2-2b-it", "params": "2.6B", "gated": True,
     "note": "Needs the Gemma license accepted on the hub"},
]

MAX_SUITABLE_PARAMS = 9e9

_downloads: dict[str, dict] = {}
_loads: dict[str, dict] = {}
_lock = threading.Lock()


def _local_path(repo_id: str) -> Path:
    return MODELS_DIR / repo_id.replace("/", "__")


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _params_label(count: int) -> str:
    if count >= 1e9:
        return f"{count / 1e9:.1f}B"
    return f"{count / 1e6:.0f}M"


def _suitability(repo_id: str, tags: list[str], params: int | None, gated) -> tuple[bool, str]:
    """Judge whether a hub model will work as a conversation partner here."""
    name = repo_id.lower()
    if "gguf" in name or "gguf" in tags:
        return False, "GGUF weights, needs llama.cpp not transformers"
    if gated:
        return False, "Gated, accept the license on huggingface.co first"
    chatty = any(k in name for k in ("instruct", "chat", "-it", "assistant")) or "conversational" in tags
    if not chatty:
        return False, "Base model, not tuned for conversation"
    if params and params > MAX_SUITABLE_PARAMS:
        return False, f"Large ({_params_label(params)}), likely too heavy for this machine"
    return True, ""


def search_models(query: str, limit: int = 20) -> list[dict]:
    """Scan the hub for text generation models and rate their suitability."""
    api = HfApi()
    kwargs = dict(search=query, filter="text-generation", sort="downloads", limit=limit)
    try:
        models = list(api.list_models(
            expand=["downloads", "likes", "tags", "gated", "safetensors"], **kwargs))
    except Exception:
        models = list(api.list_models(**kwargs))

    out = []
    for m in models:
        tags = [t.lower() for t in (getattr(m, "tags", None) or [])]
        safetensors = getattr(m, "safetensors", None)
        params = getattr(safetensors, "total", None) if safetensors else None
        gated = getattr(m, "gated", False)
        suitable, reason = _suitability(m.id, tags, params, gated)
        out.append({
            "repo_id": m.id,
            "downloads": getattr(m, "downloads", 0) or 0,
            "likes": getattr(m, "likes", 0) or 0,
            "params": _params_label(params) if params else None,
            "suitable": suitable,
            "reason": reason,
            "downloaded": _local_path(m.id).exists(),
        })
    out.sort(key=lambda x: (not x["suitable"], -x["downloads"]))
    return out


def recommended() -> list[dict]:
    """Curated starter models with their local state attached."""
    loaded = set(local_hf.loaded_models())
    out = []
    for m in RECOMMENDED:
        item = dict(m)
        item["downloaded"] = _local_path(m["repo_id"]).exists()
        item["loaded"] = m["repo_id"] in loaded
        out.append(item)
    return out


def list_local() -> list[dict]:
    """List models present on disk plus their load state."""
    out = []
    loaded = set(local_hf.loaded_models())
    for d in sorted(MODELS_DIR.iterdir()):
        if d.is_dir():
            repo_id = d.name.replace("__", "/")
            out.append({"repo_id": repo_id, "size_bytes": _dir_size(d),
                        "loaded": repo_id in loaded})
    return out


def _download_worker(repo_id: str) -> None:
    try:
        try:
            info = HfApi().model_info(repo_id, files_metadata=True)
            total = sum(f.size or 0 for f in info.siblings)
            with _lock:
                _downloads[repo_id]["total_bytes"] = total
        except Exception:
            pass
        snapshot_download(repo_id, local_dir=str(_local_path(repo_id)))
        with _lock:
            _downloads[repo_id] = {"status": "done"}
    except Exception as e:
        with _lock:
            _downloads[repo_id] = {"status": "error", "message": str(e)}
        shutil.rmtree(_local_path(repo_id), ignore_errors=True)


def start_download(repo_id: str) -> dict:
    """Begin a background snapshot download for a hub repo."""
    with _lock:
        current = _downloads.get(repo_id)
        if current and current["status"] == "downloading":
            return current
        _downloads[repo_id] = {"status": "downloading", "total_bytes": None}
    threading.Thread(target=_download_worker, args=(repo_id,), daemon=True).start()
    return {"status": "downloading"}


def download_status(repo_id: str) -> dict:
    """Current download state including byte progress when known."""
    with _lock:
        status = dict(_downloads.get(repo_id, {"status": "unknown"}))
    path = _local_path(repo_id)
    if status["status"] == "downloading" and path.exists():
        status["downloaded_bytes"] = _dir_size(path)
    elif status["status"] == "unknown" and path.exists():
        status["status"] = "done"
    return status


def _load_worker(repo_id: str) -> None:
    try:
        local_hf.load_model(repo_id, str(_local_path(repo_id)))
        registry.configure_local_model(repo_id)
        with _lock:
            _loads[repo_id] = {"status": "done"}
    except Exception as e:
        with _lock:
            _loads[repo_id] = {"status": "error", "message": str(e)}


def start_load(repo_id: str) -> dict:
    """Load a downloaded model in the background and make it the active provider."""
    if not local_hf.transformers_available():
        raise RuntimeError("transformers is not installed, see requirements-full.txt")
    if not _local_path(repo_id).exists():
        raise RuntimeError(f"{repo_id} is not downloaded yet")
    with _lock:
        current = _loads.get(repo_id)
        if current and current["status"] == "loading":
            return current
        _loads[repo_id] = {"status": "loading"}
    threading.Thread(target=_load_worker, args=(repo_id,), daemon=True).start()
    return {"status": "loading"}


def load_status(repo_id: str) -> dict:
    with _lock:
        return dict(_loads.get(repo_id, {"status": "unknown"}))


def unload(repo_id: str) -> None:
    local_hf.unload_model(repo_id)
    with _lock:
        _loads.pop(repo_id, None)


def delete(repo_id: str) -> None:
    unload(repo_id)
    shutil.rmtree(_local_path(repo_id), ignore_errors=True)
