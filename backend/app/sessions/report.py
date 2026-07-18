"""Final assessment generation at the end of a session."""

import json
import re

from .. import storage
from ..llm.registry import get_provider
from .prompts import REPORT_SYSTEM, build_report_user_prompt


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object in report response")
    return json.loads(match.group(0))


async def generate_report(session_id: str, behavior_summary: dict,
                          delivery_summary: dict | None = None,
                          keypoints_summary: dict | None = None) -> dict:
    """Ask the LLM for a structured assessment and persist it."""
    meta = storage.read_meta(session_id) or {}
    transcript = storage.read_transcript(session_id)
    provider = get_provider(meta.get("provider_id"))

    messages = [
        {"role": "system", "content": REPORT_SYSTEM},
        {"role": "user", "content": build_report_user_prompt(
            meta.get("scenario", ""), transcript, behavior_summary,
            delivery_summary, keypoints_summary)},
    ]
    raw = await provider.complete(messages, max_tokens=2000)
    try:
        report = _parse_json(raw)
    except (ValueError, json.JSONDecodeError):
        report = {
            "overall_score": None,
            "summary": raw.strip(),
            "dimensions": [], "strengths": [], "improvements": [], "notable_moments": [],
        }
    report["behavior"] = behavior_summary
    report["delivery"] = delivery_summary or {"available": False}
    report["key_points"] = keypoints_summary or {"available": False}
    report["scenario"] = meta.get("scenario", "")
    storage.write_report(session_id, report)
    storage.update_meta(session_id, status="completed", has_report=True)
    return report
