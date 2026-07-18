"""Session lifecycle REST endpoints and the live WebSocket."""

import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from pydantic import BaseModel

from .. import storage
from ..schemas import SessionCreate
from ..sessions.manager import LiveSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/sessions")
def create_session(body: SessionCreate) -> dict:
    session_id = storage.create_session({
        "scenario": body.scenario,
        "provider_id": body.provider_id,
        "duration_minutes": body.duration_minutes,
        "subtitles": body.subtitles,
        "document_ids": body.document_ids,
        "difficulty": body.difficulty,
        "key_points": [p.strip() for p in body.key_points if p.strip()],
        "pressure": body.pressure,
        "grounding": body.grounding,
    })
    return {"id": session_id}


@router.get("/api/sessions")
def list_sessions() -> list[dict]:
    return storage.list_sessions()


class ReflectionBody(BaseModel):
    answers: list[dict]


@router.post("/api/sessions/{session_id}/reflection")
def save_reflection(session_id: str, body: ReflectionBody) -> dict:
    if storage.read_meta(session_id) is None:
        raise HTTPException(404, "Session not found")
    storage.update_meta(session_id, reflection=body.answers)
    return {"ok": True}


# Graded exposure: one rung at a time, difficulty first, then pressure.
LADDER = [("easy", "off"), ("medium", "off"), ("hard", "off"),
          ("hard", "low"), ("hard", "medium"), ("hard", "high")]
STEP_UP_SCORE = 70
STEP_DOWN_SCORE = 45


def _ladder_suggestion(entries: list[dict]) -> dict | None:
    """Suggest the next session's difficulty/pressure from recent scores."""
    scored = [e for e in entries if e.get("overall_score") is not None]
    if len(scored) < 2:
        return None
    last = scored[-1]
    rung = (last.get("difficulty", "medium"), last.get("pressure", "off"))
    idx = LADDER.index(rung) if rung in LADDER else 1
    avg = (scored[-1]["overall_score"] + scored[-2]["overall_score"]) / 2
    if avg >= STEP_UP_SCORE and idx < len(LADDER) - 1:
        difficulty, pressure = LADDER[idx + 1]
        text = ("You've been solid at this level for two sessions — ready for "
                f"the next rung: {difficulty} difficulty, {pressure} pressure.")
    elif avg < STEP_DOWN_SCORE and idx > 0:
        difficulty, pressure = LADDER[idx - 1]
        text = ("No shame in consolidating: try a session at "
                f"{difficulty} difficulty, {pressure} pressure and rebuild momentum.")
    else:
        difficulty, pressure = rung
        text = "You're at the right level — keep practising here until it feels easy."
    return {"text": text, "difficulty": difficulty, "pressure": pressure}


@router.get("/api/progress")
def progress() -> dict:
    """Per-session metric time series for the longitudinal progress view."""
    entries = []
    for meta in storage.list_sessions():
        behavior = meta.get("behavior_summary") or {}
        delivery = meta.get("delivery_summary") or {}
        keypoints = meta.get("keypoints_summary") or {}
        report = storage.read_report(meta["id"]) if meta.get("has_report") else None
        key_points_pct = None
        if keypoints.get("available") and keypoints.get("total"):
            key_points_pct = round(100.0 * keypoints["covered_count"] / keypoints["total"])
        entry = {
            "id": meta["id"],
            "created_at": meta.get("created_at"),
            "scenario": meta.get("scenario", ""),
            "difficulty": meta.get("difficulty", "medium"),
            "pressure": meta.get("pressure", "off"),
            "overall_score": (report or {}).get("overall_score"),
            "filler_rate_pct": delivery.get("filler_rate_pct") if delivery.get("available") else None,
            "avg_wpm": delivery.get("avg_wpm"),
            "eye_contact_pct": behavior.get("eye_contact_pct") if behavior.get("available") else None,
            "focus_pct": behavior.get("focus_pct"),
            "gaze_drift_events": behavior.get("gaze_drift_events"),
            "confidence_score": behavior.get("confidence_score"),
            "key_points_pct": key_points_pct,
            "lost_thread_events": keypoints.get("lost_thread_events"),
        }
        # Skip sessions that ended before producing anything measurable.
        if any(entry[k] is not None for k in
               ("overall_score", "filler_rate_pct", "avg_wpm", "eye_contact_pct")):
            entries.append(entry)
    entries.sort(key=lambda e: e.get("created_at") or 0)
    return {"sessions": entries, "suggestion": _ladder_suggestion(entries)}


@router.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    meta = storage.read_meta(session_id)
    if meta is None:
        raise HTTPException(404, "Session not found")
    return {
        "meta": meta,
        "transcript": storage.read_transcript(session_id),
        "report": storage.read_report(session_id),
        "metrics_count": len(storage.read_metrics(session_id)),
    }


@router.websocket("/ws/session/{session_id}")
async def session_socket(ws: WebSocket, session_id: str) -> None:
    """Full duplex channel for audio, text, camera frames and replies."""
    await ws.accept()
    try:
        live = LiveSession(session_id, ws)
    except Exception as e:
        logger.exception("Failed to start session %s", session_id)
        await ws.send_json({"type": "error", "message": str(e)})
        await ws.close()
        return

    try:
        await live.start()
        while not live.ended:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "user_text":
                await live.handle_user_text(msg.get("text", ""))
            elif kind == "audio_chunk":
                await live.handle_audio(msg.get("pcm16_b64", ""))
            elif kind == "utterance_end":
                await live.commit_utterance()
            elif kind == "frame":
                await live.handle_frame(msg.get("jpeg_b64", ""))
            elif kind == "end":
                await live.end("user_ended")
    except WebSocketDisconnect:
        if not live.ended:
            storage.update_meta(session_id, status="disconnected")
    except Exception as e:
        logger.exception("Error in session %s", session_id)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    # Note: the shared STT instance is deliberately NOT stopped here on
    # teardown. Doing so races with the next session (this session's cleanup
    # can run after the next one has already re-entered streaming, disabling
    # it). Instead KyutaiSTT.start() resets any leftover state at the start of
    # each session, which is race free because it runs on the consumer side.
