"""Hugging Face hub integration: search, download, load local models."""

import shutil
import threading
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

from ..config import MODELS_DIR
from ..llm import local_hf

_downloads: dict[str, dict] = {}
_lock = threading.Lock()


def _local_path(repo_id: str) -> Path:
    return MODELS_DIR / repo_id.replace("/", "__")


def search_models(query: str, limit: int = 20) -> list[dict]:
    """Search the hub for text generation models matching the query."""
    api = HfApi()
    models = api.list_models(search=query, filter="text-generation",
                             sort="downloads", direction=-1, limit=limit)
    return [{
        "repo_id": m.id,
        "downloads": getattr(m, "downloads", 0),
        "likes": getattr(m, "likes", 0),
        "downloaded": _local_path(m.id).exists(),
    } for m in models]


def list_local() -> list[dict]:
    """List models present on disk plus their load state."""
    out = []
    loaded = set(local_hf.loaded_models())
    for d in sorted(MODELS_DIR.iterdir()):
        if d.is_dir():
            repo_id = d.name.replace("__", "/")
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            out.append({"repo_id": repo_id, "size_bytes": size, "loaded": repo_id in loaded})
    return out


def _download_worker(repo_id: str) -> None:
    try:
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
        _downloads[repo_id] = {"status": "downloading"}
    threading.Thread(target=_download_worker, args=(repo_id,), daemon=True).start()
    return {"status": "downloading"}


def download_status(repo_id: str) -> dict:
    with _lock:
        return _downloads.get(repo_id, {"status": "unknown"})


def load(repo_id: str) -> None:
    """Load a downloaded model for local inference."""
    if not local_hf.transformers_available():
        raise RuntimeError("transformers is not installed, see requirements-full.txt")
    path = _local_path(repo_id)
    if not path.exists():
        raise RuntimeError(f"{repo_id} is not downloaded yet")
    local_hf.load_model(repo_id, str(path))


def unload(repo_id: str) -> None:
    local_hf.unload_model(repo_id)


def delete(repo_id: str) -> None:
    local_hf.unload_model(repo_id)
    shutil.rmtree(_local_path(repo_id), ignore_errors=True)
