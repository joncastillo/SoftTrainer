"""Live behavior coaching from camera signals.

Turns the per frame face metrics from :mod:`behavior` into short,
actionable on screen tips during a session. The assessment is rule based
and fully local, so it runs in real time with no model calls.

The "brain" is deliberately isolated in :meth:`BehaviorCoach._assess`.
The surrounding cadence and cooldown logic is engine agnostic, so a later
version could swap in a vision language model that inspects frames
directly without touching any of the timing code here.
"""

import time
from typing import Optional

import numpy as np

WINDOW = 16              # most recent samples to judge on (~10s at 700ms/frame)
MIN_SAMPLES = 8          # need at least this many before saying anything
GLOBAL_COOLDOWN = 14.0   # seconds between any two tips, so it never nags
KIND_COOLDOWN = 45.0     # seconds before repeating the same kind of tip

# Thresholds are tuned against the signals produced in behavior.py and are
# intentionally forgiving: a coaching nudge should be rare and clearly earned.
FACE_MIN = 0.5           # fraction of recent frames a face must be visible
EYE_CONTACT_MIN = 0.35   # fraction of faced frames making eye contact
INSTABILITY_MAX = 0.13   # std(yaw) + std(pitch) over the window
SMILE_MIN = 0.28         # average smile ratio below which we suggest warming up
EYE_CONTACT_PRAISE = 0.8


class BehaviorCoach:
    """Watches the rolling face samples and occasionally returns one tip.

    Callers hand it the full per frame sample list on every metrics update;
    the coach decides on its own whether enough has changed, and enough
    time has passed, to be worth surfacing a single tip.
    """

    def __init__(self) -> None:
        self._last_tip_at = 0.0
        self._kind_at: dict[str, float] = {}
        self._praised = False

    def observe(self, samples: list[dict]) -> Optional[dict]:
        """Return one tip dict ``{text, kind, tone}`` or ``None``."""
        now = time.monotonic()
        if now - self._last_tip_at < GLOBAL_COOLDOWN:
            return None

        recent = samples[-WINDOW:]
        if len(recent) < MIN_SAMPLES:
            return None

        faced = [s for s in recent if s.get("face")]
        if len(faced) / len(recent) < FACE_MIN:
            return self._maybe(now, "framing",
                               "I can't see your face clearly. Try centering yourself in the camera.")
        if len(faced) < MIN_SAMPLES:
            return None

        assessment = self._assess(faced)
        if assessment is None:
            return None
        kind, text, tone = assessment
        return self._maybe(now, kind, text, tone)

    def _assess(self, faced: list[dict]) -> Optional[tuple[str, str, str]]:
        """The rule based brain: pick the single most useful nudge, if any.

        Swap this method (or inject an alternative) to drive coaching from a
        different source such as a vision language model.
        """
        eye = sum(1 for s in faced if s.get("eye_contact")) / len(faced)
        yaws = np.array([s.get("yaw", 0.0) for s in faced], dtype=float)
        pitches = np.array([s.get("pitch", 0.0) for s in faced], dtype=float)
        instability = float(np.std(yaws) + np.std(pitches))
        smile = float(np.mean([s.get("smile", 0.0) for s in faced]))

        if eye < EYE_CONTACT_MIN:
            return ("eye_contact",
                    "You're looking away from the camera a lot. Try to meet it more often.", "nudge")
        if instability > INSTABILITY_MAX:
            return ("steadiness",
                    "Try to keep your head a little steadier. Small movements can read as nerves.", "nudge")
        if smile < SMILE_MIN:
            return ("warmth",
                    "Relax your expression a touch. A light smile comes across as warmer.", "nudge")
        if eye > EYE_CONTACT_PRAISE and instability < INSTABILITY_MAX * 0.6 and not self._praised:
            self._praised = True
            return ("praise", "Nice presence. Steady eye contact and a calm posture.", "positive")
        return None

    def _maybe(self, now: float, kind: str, text: str, tone: str = "nudge") -> Optional[dict]:
        """Emit a tip unless this kind is still within its cooldown."""
        if now - self._kind_at.get(kind, -1e9) < KIND_COOLDOWN:
            return None
        self._last_tip_at = now
        self._kind_at[kind] = now
        return {"kind": kind, "text": text, "tone": tone}
