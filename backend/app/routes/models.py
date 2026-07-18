"""Hugging Face model manager endpoints."""

from fastapi import APIRouter, HTTPException

from ..hub import manager
from ..schemas import DownloadRequest, LoadRequest

router = APIRouter()


@router.get("/api/models/recommended")
def recommended() -> list[dict]:
    return manager.recommended()


@router.get("/api/models/search")
def search(q: str, limit: int = 20) -> list[dict]:
    try:
        return manager.search_models(q, limit=limit)
    except Exception as e:
        raise HTTPException(502, f"Hub search failed: {e}")


@router.get("/api/models/local")
def local() -> list[dict]:
    return manager.list_local()


@router.post("/api/models/download")
def download(body: DownloadRequest) -> dict:
    return manager.start_download(body.repo_id)


@router.get("/api/models/download-status")
def download_status(repo_id: str) -> dict:
    return manager.download_status(repo_id)


@router.post("/api/models/load")
def load(body: LoadRequest) -> dict:
    try:
        return manager.start_load(body.repo_id)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/api/models/load-status")
def load_status(repo_id: str) -> dict:
    return manager.load_status(repo_id)


@router.post("/api/models/unload")
def unload(body: LoadRequest) -> dict:
    manager.unload(body.repo_id)
    return {"ok": True}


@router.delete("/api/models/{repo_id:path}")
def delete(repo_id: str) -> dict:
    manager.delete(repo_id)
    return {"ok": True}
