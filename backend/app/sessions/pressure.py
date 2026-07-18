"""Pressure training: scheduled heckles and distractions, plus composure scoring.

When the user opts into pressure, a director task interjects audience
heckles (spoken and shown on screen) and ambient distractions (shown on
screen) at a cadence set by the pressure level. Everything is local and
scripted: the point is the *stimulus*, not clever writing, and canned
lines keep latency and token use at zero.

The same module scores composure by comparing how the user's delivery
and eye contact hold up in the window right after each event against
their baseline everywhere else.
"""

import asyncio
import base64
import random
import time
from typing import TYPE_CHECKING, Optional

from .. import storage
from ..speech import engines

if TYPE_CHECKING:
    from .manager import LiveSession

# Seconds between events (mean, jitter fraction) per level.
LEVELS = {
    "low": (150.0, 0.4),
    "medium": (90.0, 0.4),
    "high": (50.0, 0.35),
}
FIRST_EVENT_GRACE = 45.0   # let the session settle before the first event
POST_WINDOW = 30.0         # seconds after an event that count as "under pressure"

# Fraction of events that deliberately wait for the user to be mid-sentence
# before cutting in; the rest fire on the timer wherever it lands.
INTERRUPT_PROB = {"low": 0.3, "medium": 0.5, "high": 0.7}
INTERRUPT_MIN_SPEECH = 2.5   # seconds into an utterance before barging in
INTERRUPT_WAIT_MAX = 40.0    # give up waiting for speech and fire anyway

HECKLES = [
    "Sorry, but I'm not convinced. Why should we believe that?",
    "That's what everyone says. What makes you different?",
    "Can you get to the point? We don't have all day.",
    "I heard your competitor does this better and cheaper.",
    "Hold on — that doesn't match what you said earlier.",
    "You're losing me. Explain it like I'm not an expert.",
    "Numbers, please. Do you actually have any numbers?",
    "With respect, I've seen a dozen pitches exactly like this.",
]

# Phrased as barge-ins: these land while the user is mid-sentence.
INTERRUPT_HECKLES = [
    "Hold on, hold on. Before you go any further, why should we care?",
    "Sorry to cut you off, but I've heard this part before. Skip ahead.",
    "Let me stop you right there. That's not answering my question.",
    "Wait, wait. Say that again, but simpler this time.",
    "I'm going to interrupt. What's the actual bottom line here?",
]

DISTRACTIONS = [
    "Someone's phone goes off loudly in the room.",
    "Two people in the back start a side conversation.",
    "A notification pops up on the shared screen.",
    "Someone gets up and walks out mid-sentence.",
    "There's a loud noise from the hallway.",
    "Your counterpart glances at their watch and sighs.",
]


class PressureDirector:
    """Fires scheduled pressure events and remembers when they happened."""

    def __init__(self, level: str) -> None:
        self.level = level if level in LEVELS else "off"
        self.event_times: list[float] = []   # monotonic timestamps
        self.event_count = 0
        self.interrupt_count = 0
        self._task: Optional[asyncio.Task] = None
        self._recent: list[str] = []

    @property
    def enabled(self) -> bool:
        return self.level in LEVELS

    def start(self, session: "LiveSession") -> None:
        if self.enabled:
            self._task = asyncio.create_task(self._run(session))

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def _next_delay(self, first: bool) -> float:
        mean, jitter = LEVELS[self.level]
        delay = mean * random.uniform(1 - jitter, 1 + jitter)
        return max(delay, FIRST_EVENT_GRACE) if first else delay

    def _pick(self, pool: list[str]) -> str:
        fresh = [line for line in pool if line not in self._recent] or pool
        line = random.choice(fresh)
        self._recent = (self._recent + [line])[-6:]
        return line

    async def _run(self, session: "LiveSession") -> None:
        first = True
        while not session.ended:
            await asyncio.sleep(self._next_delay(first))
            first = False
            if session.ended or session.seconds_left() < 30:
                return
            # Some events specifically hunt for a mid-sentence moment; and
            # any event that happens to land during speech is a barge-in.
            if random.random() < INTERRUPT_PROB[self.level]:
                await self._wait_for_speech(session)
            if session.ended or session.seconds_left() < 30:
                return
            interrupt = session.user_speaking_seconds() > 0.5
            await self._fire(session, interrupt)

    @staticmethod
    async def _wait_for_speech(session: "LiveSession") -> None:
        deadline = time.monotonic() + INTERRUPT_WAIT_MAX
        while time.monotonic() < deadline and not session.ended:
            if session.user_speaking_seconds() >= INTERRUPT_MIN_SPEECH:
                return
            await asyncio.sleep(0.5)

    async def _fire(self, session: "LiveSession", interrupt: bool = False) -> None:
        heckle = interrupt or random.random() < 0.6
        kind = "heckle" if heckle else "distraction"
        pool = INTERRUPT_HECKLES if interrupt else (HECKLES if heckle else DISTRACTIONS)
        text = self._pick(pool)
        self.event_times.append(time.monotonic())
        self.event_count += 1
        if interrupt:
            self.interrupt_count += 1
        storage.append_transcript(session.id, {
            "role": "event", "kind": kind, "text": text, "interrupt": interrupt})
        await session.send({"type": "pressure_event", "kind": kind, "text": text,
                            "interrupt": interrupt})
        if heckle and engines.tts_installed():
            try:
                wav = await engines.synthesize_async(text)
                if wav:
                    # The heckler channel plays immediately on the client,
                    # over the user's own voice, instead of queueing behind
                    # trainer speech: that is what makes it an interruption.
                    await session.send({"type": "tts_audio", "channel": "heckler",
                                        "wav_b64": base64.b64encode(wav).decode()})
            except Exception:
                pass  # a silent heckle still lands on screen

    def under_pressure(self, t: float) -> bool:
        return any(0 <= t - e <= POST_WINDOW for e in self.event_times)

    def composure_summary(self, delivery_records: list[dict],
                          behavior_samples: list[dict]) -> dict:
        """Compare delivery and focus after events against the baseline.

        ``delivery_records`` are per-utterance dicts with monotonic ``t``,
        ``words`` and ``fillers``; ``behavior_samples`` are per-frame dicts
        with monotonic ``t`` plus the usual face metrics.
        """
        if not self.enabled or not self.event_times:
            return {"available": False, "events": self.event_count}

        out: dict = {"available": True, "events": self.event_count, "level": self.level,
                     "interruptions_mid_sentence": self.interrupt_count}

        pressured = [r for r in delivery_records if self.under_pressure(r["t"])]
        calm = [r for r in delivery_records if not self.under_pressure(r["t"])]
        if pressured and calm:
            def rate(rs: list[dict]) -> Optional[float]:
                words = sum(r["words"] for r in rs)
                return round(100.0 * sum(r["fillers"] for r in rs) / words, 1) if words else None
            out["filler_rate_baseline_pct"] = rate(calm)
            out["filler_rate_under_pressure_pct"] = rate(pressured)

        faced = [s for s in behavior_samples if s.get("face") and "t" in s]
        pressured_f = [s for s in faced if self.under_pressure(s["t"])]
        calm_f = [s for s in faced if not self.under_pressure(s["t"])]
        if len(pressured_f) >= 4 and len(calm_f) >= 4:
            def contact(ss: list[dict]) -> float:
                return round(100.0 * sum(1 for s in ss if s.get("eye_contact")) / len(ss), 1)
            out["eye_contact_baseline_pct"] = contact(calm_f)
            out["eye_contact_under_pressure_pct"] = contact(pressured_f)

        return out
