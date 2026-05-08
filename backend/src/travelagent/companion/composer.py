"""Notification composer.

Two implementations live behind one interface:

  * `HeuristicComposer` — template-based, deterministic, always available.
  * `DspyComposer` — uses dspy.ChainOfThought to compose; falls back to
    the heuristic if dspy or the LLM endpoint isn't available.

Per the brief (pp. 61–63), the message must be correct, toned, and
concise (<=120 words), with explicit delay duration, attendees,
proposed times, and a fallback option.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NotificationContext:
    user_name: str
    delay_minutes: int
    delay_reason: str
    meeting_title: str
    attendees: list
    original_meeting_time: datetime
    proposed_times: list  # list[datetime]
    weather_condition: str
    fallback: str = "I can dial in from the car once I'm out of the airport."


class HeuristicComposer:
    """Template-based composer used as the fine-tuning baseline."""

    def compose(self, ctx: NotificationContext) -> str:
        attendee_str = ", ".join(a.split("@")[0] for a in ctx.attendees) or "team"
        proposed_str = ", ".join(t.strftime("%I:%M %p").lstrip("0") for t in ctx.proposed_times[:3])
        msg = (
            f"Hi {attendee_str} — my flight is running about {ctx.delay_minutes} minutes late"
            f"{' (' + ctx.delay_reason + ')' if ctx.delay_reason else ''}, "
            f"so I won't make our {ctx.original_meeting_time.strftime('%I:%M %p').lstrip('0')} "
            f"{ctx.meeting_title}. "
            f"Could we move to one of: {proposed_str}? "
            f"If none work, {ctx.fallback} "
            f"— {ctx.user_name}"
        )
        return msg


class DspyComposer:
    """DSPy ChainOfThought composer (optional)."""

    def __init__(self):
        self._available = False
        self._program = None
        self._fallback = HeuristicComposer()
        try:
            import dspy  # noqa: F401
            self._available = True
            self._build_program()
        except Exception:
            self._available = False

    def _build_program(self):
        import dspy

        class NotifySig(dspy.Signature):
            """Compose a brief, polite meeting-reschedule message under 120 words."""
            delay_scenario = dspy.InputField(desc="JSON-ish description of the delay")
            notification = dspy.OutputField(desc="Notification text, <=120 words")

        self._program = dspy.ChainOfThought(NotifySig)

    def compose(self, ctx: NotificationContext) -> str:
        if not self._available or self._program is None:
            return self._fallback.compose(ctx)
        try:
            scenario = (
                f"User: {ctx.user_name}; delay: {ctx.delay_minutes}m ({ctx.delay_reason}); "
                f"meeting: {ctx.meeting_title} at {ctx.original_meeting_time}; "
                f"attendees: {ctx.attendees}; "
                f"proposed: {[t.isoformat() for t in ctx.proposed_times]}; "
                f"weather: {ctx.weather_condition}; "
                f"fallback: {ctx.fallback}"
            )
            result = self._program(delay_scenario=scenario)
            return getattr(result, "notification", "") or self._fallback.compose(ctx)
        except Exception:
            return self._fallback.compose(ctx)


# ---------------------------------------------------------------------------
# Verifiable rewards (RLVR signal — pp. 62)
# ---------------------------------------------------------------------------

def reward_correct(message: str, ctx: NotificationContext) -> float:
    score = 0.0
    if str(ctx.delay_minutes) in message:
        score += 0.25
    if ctx.attendees:
        hits = sum(1 for a in ctx.attendees if a.split("@")[0].lower() in message.lower())
        score += min(0.25, 0.25 * hits / max(1, len(ctx.attendees)))
    else:
        score += 0.25
    if ctx.proposed_times and any(
        t.strftime("%I:%M").lstrip("0") in message for t in ctx.proposed_times
    ):
        score += 0.25
    if "dial in" in message.lower() or "call" in message.lower() or ctx.fallback[:20].lower() in message.lower():
        score += 0.25
    return round(score, 3)


def reward_concise(message: str) -> float:
    words = len(message.split())
    if words <= 120:
        return 1.0
    return max(0.0, 1.0 - 0.1 * (words - 120))


def reward_tone(message: str) -> float:
    # Cheap proxy classifier: rewards apologetic + warm without groveling.
    lower = message.lower()
    polite_signals = sum(s in lower for s in ("hi ", "thanks", "could we", "if none"))
    grovel = lower.count("so sorry") + lower.count("very sorry") + lower.count("apologies")
    score = min(1.0, 0.4 + 0.15 * polite_signals) - 0.2 * max(0, grovel - 1)
    return max(0.0, min(1.0, score))


def composite_reward(message: str, ctx: NotificationContext,
                     alpha: float = 0.5, beta: float = 0.3, gamma: float = 0.2) -> dict:
    rc = reward_correct(message, ctx)
    rt = reward_tone(message)
    rcon = reward_concise(message)
    return {
        "r_correct": rc,
        "r_tone": rt,
        "r_concise": rcon,
        "composite": round(alpha * rc + beta * rt + gamma * rcon, 3),
    }
