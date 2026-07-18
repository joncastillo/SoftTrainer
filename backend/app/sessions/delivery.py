"""Delivery analysis from user speech: filler words and speaking pace.

Runs on the transcript text of each user utterance (fully local, no audio
model needed) and, like the behavior coach, occasionally surfaces one short
live tip. It also produces a session summary for the final report.

Pace (words per minute) is only computed for spoken turns, where we know how
long the utterance took; typed turns still contribute filler statistics.
"""

import re
import time
from typing import Optional

# Conservative list: words that are almost always fillers in context. The
# highly ambiguous ones ("so", "well", "like", "right") are deliberately left
# out for now to avoid over-counting ordinary speech.
FILLERS = [
    "um", "uh", "uhm", "erm", "hmm", "mhm",
    "you know", "i mean", "sort of", "kind of", "basically", "literally",
]
_FILLER_RE = re.compile(
    r"\b(" + "|".join(f.replace(" ", r"\s+") for f in FILLERS) + r")\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z']+")

MIN_WORDS = 12            # need a substantial utterance before judging live
FILLER_RATE_HIGH = 0.08   # fillers per word
WPM_FAST = 180
WPM_SLOW = 95
GLOBAL_COOLDOWN = 20.0    # seconds between any two delivery tips
KIND_COOLDOWN = 60.0      # seconds before repeating the same kind of tip


class DeliveryAnalyzer:
    """Accumulates filler and pace stats and emits occasional live tips."""

    def __init__(self) -> None:
        self.total_words = 0
        self.total_fillers = 0
        self.total_speech_seconds = 0.0
        self.utterances = 0
        self._last_tip_at = 0.0
        self._kind_at: dict[str, float] = {}

    @staticmethod
    def _count(text: str) -> tuple[int, int]:
        return len(_WORD_RE.findall(text)), len(_FILLER_RE.findall(text))

    def observe(self, text: str, duration: Optional[float] = None) -> Optional[dict]:
        """Record one user utterance; maybe return a single coaching tip."""
        words, fillers = self._count(text)
        if not words:
            return None
        self.total_words += words
        self.total_fillers += fillers
        self.utterances += 1
        if duration and duration > 0:
            self.total_speech_seconds += duration
        return self._tip(words, fillers, duration)

    def _tip(self, words: int, fillers: int, duration: Optional[float]) -> Optional[dict]:
        now = time.monotonic()
        if now - self._last_tip_at < GLOBAL_COOLDOWN or words < MIN_WORDS:
            return None
        if fillers >= 2 and fillers / words >= FILLER_RATE_HIGH:
            return self._emit(now, "fillers",
                              f"Watch the filler words ({fillers} in that answer). A short pause beats an 'um'.")
        if duration and duration > 0:
            wpm = words / (duration / 60.0)
            if wpm > WPM_FAST:
                return self._emit(now, "pace_fast",
                                  "You're speaking quite fast. Slow down and let your points breathe.")
            if wpm < WPM_SLOW and words >= 20:
                return self._emit(now, "pace_slow",
                                  "Your pace is a little slow. A bit more energy will land better.")
        return None

    def _emit(self, now: float, kind: str, text: str) -> Optional[dict]:
        if now - self._kind_at.get(kind, -1e9) < KIND_COOLDOWN:
            return None
        self._last_tip_at = now
        self._kind_at[kind] = now
        return {"kind": kind, "text": text, "tone": "nudge"}

    def summary(self) -> dict:
        """Session level delivery metrics for the final report."""
        if not self.total_words:
            return {"available": False}
        out = {
            "available": True,
            "utterances": self.utterances,
            "total_words": self.total_words,
            "filler_count": self.total_fillers,
            "filler_rate_pct": round(100.0 * self.total_fillers / self.total_words, 1),
        }
        if self.total_speech_seconds > 0:
            out["avg_wpm"] = round(self.total_words / (self.total_speech_seconds / 60.0))
        return out
