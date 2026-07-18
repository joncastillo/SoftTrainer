"""Disk persistence for sessions, transcripts, metrics and reports."""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .config import SESSIONS_DIR


def _session_dir(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


def create_session(meta: dict[str, Any]) -> str:
    """Create a session folder and persist its metadata, returns the id."""
    session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    d = _session_dir(session_id)
    d.mkdir(parents=True)
    meta = {**meta, "id": session_id, "created_at": time.time(), "status": "created"}
    write_meta(session_id, meta)
    (d / "transcript.json").write_text("[]", encoding="utf-8")
    return session_id


def write_meta(session_id: str, meta: dict[str, Any]) -> None:
    path = _session_dir(session_id) / "meta.json"
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def read_meta(session_id: str) -> Optional[dict[str, Any]]:
    path = _session_dir(session_id) / "meta.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def update_meta(session_id: str, **fields: Any) -> dict[str, Any]:
    meta = read_meta(session_id) or {"id": session_id}
    meta.update(fields)
    write_meta(session_id, meta)
    return meta


def append_transcript(session_id: str, entry: dict[str, Any]) -> None:
    """Append one utterance to the session transcript on disk."""
    path = _session_dir(session_id) / "transcript.json"
    transcript = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    transcript.append({**entry, "ts": time.time()})
    path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")


def read_transcript(session_id: str) -> list[dict[str, Any]]:
    path = _session_dir(session_id) / "transcript.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_metrics(session_id: str, sample: dict[str, Any]) -> None:
    path = _session_dir(session_id) / "metrics.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**sample, "ts": time.time()}) + "\n")


def read_metrics(session_id: str) -> list[dict[str, Any]]:
    path = _session_dir(session_id) / "metrics.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_report(session_id: str, report: dict[str, Any]) -> None:
    path = _session_dir(session_id) / "report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def read_report(session_id: str) -> Optional[dict[str, Any]]:
    path = _session_dir(session_id) / "report.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_sessions() -> list[dict[str, Any]]:
    """Return session metadata for all sessions, newest first."""
    out = []
    for d in sorted(SESSIONS_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "meta.json").exists():
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            meta["has_report"] = (d / "report.json").exists()
            out.append(meta)
    return out
