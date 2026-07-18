"""Document upload and RAG management endpoints."""

from fastapi import APIRouter, HTTPException, UploadFile

from ..rag import store

router = APIRouter()


@router.post("/api/documents")
async def upload_document(file: UploadFile) -> dict:
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "File too large, 25 MB max")
    try:
        return store.add_document(file.filename or "upload.txt", raw)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/documents")
def list_documents() -> list[dict]:
    return store.list_documents()


@router.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> dict:
    store.delete_document(doc_id)
    return {"ok": True}
