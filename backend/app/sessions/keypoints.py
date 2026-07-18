"""Key point coverage tracking and lost-thread detection from user speech.

The user can name a few key points they want to land before the session
starts. Matching is fully local and lexical: a point counts as covered
once most of its content words have been heard across the user's turns,
with fuzzy word matching so STT noise and inflections still count.

The same module watches for signs of losing the train of thought
(explicit phrases like "where was I", or stuttered phrase restarts) and
answers with a recovery tip anchored to the next uncovered key point.
"""

import re
import time
from difflib import SequenceMatcher
from typing import Optional

MAX_POINTS = 5
COVER_RATIO = 0.6         # fraction of a point's content words heard to call it covered
FUZZY_RATIO = 0.84        # difflib similarity for a word match
GLOBAL_COOLDOWN = 20.0    # seconds between any two tips from this tracker
KIND_COOLDOWN = 45.0      # seconds before repeating the same kind of tip
REMINDER_AT = 0.6         # session fraction after which uncovered points get a nudge

_WORD_RE = re.compile(r"[a-z']+")
STOPWORDS = frozenset("""
a an the and or but if then than so of to in on at for with about into over
after before by from up down out off is are was were be been being am do does
did have has had will would can could should may might must not no i you he
she it we they me him her them my your his its our their this that these
those there here what which who whom when where why how as because while
want wants wanted need needs like talk talks say says said mention discuss
""".split())

LOST_THREAD_RE = re.compile(
    r"\b(where was i|lost my (train of thought|thread|place)|"
    r"what was i (saying|talking about)|let me start (over|again)|"
    r"i forgot (what|where) i was|going blank|my mind (went|is going) blank|"
    r"sorry,? i lost)\b", re.IGNORECASE)


def _content_words(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower())
            if len(w) >= 3 and w not in STOPWORDS]


def _words_match(a: str, b: str) -> bool:
    if a == b:
        return True
    # Shared stem: one word extending the other covers inflections cheaply.
    if len(a) >= 4 and len(b) >= 4 and (a.startswith(b[:4]) and b.startswith(a[:4])):
        if a.startswith(b) or b.startswith(a):
            return True
    return SequenceMatcher(None, a, b).ratio() >= FUZZY_RATIO


def _stutter_restarts(text: str) -> int:
    """Count immediately repeated 2-3 word runs, a sign of restarting a phrase."""
    words = _WORD_RE.findall(text.lower())
    hits = 0
    for n in (2, 3):
        i = 0
        while i + 2 * n <= len(words):
            if words[i:i + n] == words[i + n:i + 2 * n]:
                hits += 1
                i += 2 * n
            else:
                i += 1
    return hits


class KeyPointTracker:
    """Tracks coverage of the user's key points and thread-loss moments."""

    def __init__(self, points: list[str]) -> None:
        cleaned = [p.strip() for p in points if p and p.strip()][:MAX_POINTS]
        self._points = [{"text": p, "covered": False,
                         "words": _content_words(p), "hits": set()}
                        for p in cleaned]
        self.lost_thread_events = 0
        self._last_tip_at = 0.0
        self._kind_at: dict[str, float] = {}
        self._reminded = False

    @property
    def enabled(self) -> bool:
        return bool(self._points)

    def points(self) -> list[dict]:
        """Client-facing coverage state for the live checklist."""
        return [{"text": p["text"], "covered": p["covered"]} for p in self._points]

    def _next_uncovered(self) -> Optional[str]:
        for p in self._points:
            if not p["covered"]:
                return p["text"]
        return None

    def observe(self, text: str, elapsed_fraction: float) -> tuple[bool, Optional[dict]]:
        """Digest one user utterance.

        Returns ``(coverage_changed, tip)`` where ``tip`` is at most one
        coaching message: thread-loss recovery beats coverage reminders.
        """
        changed = self._update_coverage(text)
        tip = self._lost_thread_tip(text)
        if tip is None:
            tip = self._reminder_tip(elapsed_fraction)
        return changed, tip

    def _update_coverage(self, text: str) -> bool:
        heard = _content_words(text)
        if not heard:
            return False
        changed = False
        for p in self._points:
            if p["covered"] or not p["words"]:
                continue
            for i, want in enumerate(p["words"]):
                if i not in p["hits"] and any(_words_match(want, w) for w in heard):
                    p["hits"].add(i)
            if len(p["hits"]) / len(p["words"]) >= COVER_RATIO:
                p["covered"] = True
                changed = True
        return changed

    def _lost_thread_tip(self, text: str) -> Optional[dict]:
        if not (LOST_THREAD_RE.search(text) or _stutter_restarts(text) >= 2):
            return None
        self.lost_thread_events += 1
        anchor = self._next_uncovered()
        if anchor:
            msg = f"Lost the thread? Take a breath — pick up with \"{anchor}\"."
        else:
            msg = "Lost the thread? Pause, breathe, and restate your last point in one sentence."
        return self._emit("lost_thread", msg)

    def _reminder_tip(self, elapsed_fraction: float) -> Optional[dict]:
        if not self.enabled or self._reminded or elapsed_fraction < REMINDER_AT:
            return None
        missing = self._next_uncovered()
        if missing is None:
            return None
        tip = self._emit("keypoint_reminder",
                         f"You haven't touched on \"{missing}\" yet — bring it in soon.")
        # Only latch once the nudge actually made it past the cooldowns.
        self._reminded = tip is not None
        return tip

    def _emit(self, kind: str, text: str) -> Optional[dict]:
        now = time.monotonic()
        if now - self._last_tip_at < GLOBAL_COOLDOWN:
            return None
        if now - self._kind_at.get(kind, -1e9) < KIND_COOLDOWN:
            return None
        self._last_tip_at = now
        self._kind_at[kind] = now
        return {"kind": kind, "text": text, "tone": "nudge"}

    def summary(self) -> dict:
        """Session-level coverage result for the final report."""
        if not self.enabled:
            return {"available": False, "lost_thread_events": self.lost_thread_events}
        covered = sum(1 for p in self._points if p["covered"])
        return {
            "available": True,
            "points": self.points(),
            "covered_count": covered,
            "total": len(self._points),
            "lost_thread_events": self.lost_thread_events,
        }
