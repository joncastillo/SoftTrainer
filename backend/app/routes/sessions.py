"""Session lifecycle REST endpoints and the live WebSocket."""

import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .. import storage
from ..schemas import SessionCreate
from ..sessions.manager import LiveSession

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
    })
    return {"id": session_id}


@router.get("/api/sessions")
def list_sessions() -> list[dict]:
    return storage.list_sessions()


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
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
