"""Document store with embedding search.

Uses sentence-transformers when installed, otherwise a hashed bag of
words embedding that needs no extra dependencies. Vectors and chunks
are persisted per document under the documents data dir.
"""

import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

from ..config import DOCUMENTS_DIR
from .extract import chunk_text, extract_text

_st_model = None
_HASH_DIM = 512


def _embedder():
    global _st_model
    if _st_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            _st_model = "hash"
    return _st_model


def _hash_embed(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), _HASH_DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % _HASH_DIM
            vectors[i, idx] += 1.0
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def embed(texts: list[str]) -> np.ndarray:
    model = _embedder()
    if model == "hash":
        return _hash_embed(texts)
    return np.asarray(model.encode(texts, normalize_embeddings=True), dtype=np.float32)


def add_document(filename: str, raw: bytes) -> dict:
    """Ingest an uploaded file: save, extract, chunk, embed, persist."""
    doc_id = uuid.uuid4().hex[:12]
    d = DOCUMENTS_DIR / doc_id
    d.mkdir(parents=True)
    original = d / filename
    original.write_bytes(raw)

    text = extract_text(original)
    chunks = chunk_text(text)
    if not chunks:
        shutil.rmtree(d)
        raise ValueError("No text could be extracted from the document")

    vectors = embed(chunks)
    np.save(d / "vectors.npy", vectors)
    meta = {
        "id": doc_id,
        "filename": filename,
        "created_at": time.time(),
        "chunks": len(chunks),
        "embedding": "sentence-transformers" if _embedder() != "hash" else "hashed",
    }
    (d / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def list_documents() -> list[dict]:
    out = []
    for d in sorted(DOCUMENTS_DIR.iterdir()):
        meta_file = d / "meta.json"
        if meta_file.exists():
            out.append(json.loads(meta_file.read_text(encoding="utf-8")))
    return out


def delete_document(doc_id: str) -> None:
    d = DOCUMENTS_DIR / doc_id
    if d.exists():
        shutil.rmtree(d)


def _load_doc(doc_id: str) -> Optional[tuple[list[str], np.ndarray]]:
    d = DOCUMENTS_DIR / doc_id
    if not (d / "chunks.json").exists():
        return None
    chunks = json.loads((d / "chunks.json").read_text(encoding="utf-8"))
    vectors = np.load(d / "vectors.npy")
    return chunks, vectors


def search(query: str, doc_ids: list[str], top_k: int = 4) -> list[dict]:
    """Return the most relevant chunks across the given documents."""
    if not doc_ids:
        return []
    query_vec = embed([query])[0]
    scored: list[dict] = []
    for doc_id in doc_ids:
        loaded = _load_doc(doc_id)
        if loaded is None:
            continue
        chunks, vectors = loaded
        scores = vectors @ query_vec
        for i in np.argsort(scores)[::-1][:top_k]:
            scored.append({"doc_id": doc_id, "text": chunks[int(i)], "score": float(scores[int(i)])})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]
