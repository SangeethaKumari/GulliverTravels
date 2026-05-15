"""The committee: Time, Risk, and Impact agents.

Per the capstone brief (pp. 53–55), each agent reasons about its own
domain and emits a probability/score with a confidence interval. The
orchestrator then synthesizes the three outputs into a decision.

These are implemented as deterministic Python classes (no LLM calls)
so the architecture is testable and reproducible. An LLM-backed
variant could be slotted in trivially via the same interface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import mcp_tools, mocks
from .signals import TimeSignal, RiskSignal, ImpactSignal


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

@dataclass
class TimeAgentOutput:
    p_arrive_by_deadline: float
    median_arrival: datetime
    percentile_10: datetime  # best case
    percentile_90: datetime  # worst case
    rationale: str

    @property
    def signal(self) -> TimeSignal:
        return TimeSignal.from_probability(self.p_arrive_by_deadline)


@dataclass
class RiskAgentOutput:
    delay_multiplier: float  # in [1.0, 2.0]
    risk_factors: list
    confidence: float
    rationale: str

    @property
    def signal(self) -> RiskSignal:
        return RiskSignal.from_multiplier(self.delay_multiplier, self.risk_factors)


@dataclass
class ImpactAgentOutput:
    meeting_weight: float  # in [0, 1]
    attendee_list: list
    cancellation_flexibility: float
    rationale: str

    @property
    def signal(self) -> ImpactSignal:
        return ImpactSignal.from_weight(self.meeting_weight)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class TimeAgent:
    """Estimates P(arrive at meeting by deadline)."""

    DOMESTIC_TERMINAL_MIN = 15
    INTL_TERMINAL_MIN = 40
    RIDE_BUFFER_MIN = 5

    def assess(self, flight: dict, route: dict, ride_eta_min: int,
               meeting_start: datetime, international: bool = False) -> TimeAgentOutput:
        if flight["currentStatus"] == "cancelled":
            return TimeAgentOutput(
                p_arrive_by_deadline=0.0,
                median_arrival=meeting_start + timedelta(hours=24),
                percentile_10=meeting_start + timedelta(hours=12),
                percentile_90=meeting_start + timedelta(hours=48),
                rationale="Flight cancelled — arrival not possible by deadline.",
            )

        landing = datetime.fromisoformat(flight["estimatedLanding"])
        terminal = self.INTL_TERMINAL_MIN if international else self.DOMESTIC_TERMINAL_MIN
        ride_wait = ride_eta_min + self.RIDE_BUFFER_MIN
        drive_min = route["durationSeconds"] / 60
        drive_free_min = route["durationInFreeFlowSeconds"] / 60

        median_arrival = landing + timedelta(minutes=terminal + ride_wait + drive_min)
        best_arrival = landing + timedelta(minutes=terminal * 0.7 + ride_wait * 0.6 + drive_free_min)
        worst_arrival = landing + timedelta(minutes=terminal * 1.4 + ride_wait * 1.6 + drive_min * 1.3)

        # Probability via an exponential slack model: each ~15min of slack
        # roughly halves the residual risk of missing the deadline.
        if median_arrival <= meeting_start:
            slack_min = (meeting_start - median_arrival).total_seconds() / 60
            p = 1.0 - 0.5 * math.exp(-slack_min / 15.0)
            p = min(p, 0.98)
        else:
            overshoot_min = (median_arrival - meeting_start).total_seconds() / 60
            p = 0.5 * math.exp(-overshoot_min / 20.0)
            p = max(p, 0.02)

        rationale = (
            f"Land at {landing.strftime('%H:%M')}, +{terminal}m terminal, "
            f"+{ride_wait}m ride, +{drive_min:.0f}m drive. "
            f"Median arrival {median_arrival.strftime('%H:%M')} vs deadline "
            f"{meeting_start.strftime('%H:%M')}."
        )
        return TimeAgentOutput(
            p_arrive_by_deadline=round(p, 3),
            median_arrival=median_arrival,
            percentile_10=best_arrival,
            percentile_90=worst_arrival,
            rationale=rationale,
        )


class RiskAgent:
    """Adjusts the time estimate by reasoning about volatility."""

    def assess(self, flight: dict, weather: dict) -> RiskAgentOutput:
        factors = []
        multiplier = 1.0
        if weather["trend"] == "worsening":
            factors.append("weather_worsening")
            multiplier += 0.15
        if weather["current"]["condition"] in ("rain", "snow"):
            factors.append(f"adverse_weather_{weather['current']['condition']}")
            multiplier += 0.10
        if flight.get("delayTrend") == "increasing":
            factors.append("delay_trend_up")
            multiplier += 0.20
        if flight.get("delayMinutes", 0) > 60:
            factors.append("significant_delay")
            multiplier += 0.05

        multiplier = min(multiplier, 2.0)
        confidence = 0.85 if len(factors) <= 2 else 0.70
        rationale = (
            f"Risk multiplier {multiplier:.2f} from factors: "
            f"{', '.join(factors) if factors else 'none — conditions stable'}."
        )
        return RiskAgentOutput(
            delay_multiplier=round(multiplier, 2),
            risk_factors=factors,
            confidence=confidence,
            rationale=rationale,
        )


class ImpactAgent:
    """Scores the meeting's importance from calendar metadata."""

    HIGH_SIGNAL_KEYWORDS = {
        "board", "investor", "client", "presentation",
        "critical", "ceo", "interview", "kickoff",
    }

    def assess(self, event: dict) -> ImpactAgentOutput:
        attendees = event.get("attendees", [])
        keywords_text = (event.get("title", "") + " " + event.get("description", "")).lower()
        keyword_hits = sum(1 for kw in self.HIGH_SIGNAL_KEYWORDS if kw in keywords_text)

        weight = 0.2
        weight += min(0.4, len(attendees) * 0.05)
        weight += min(0.4, keyword_hits * 0.15)
        if event.get("required"):
            weight += 0.05
        weight = min(weight, 1.0)

        # Cancellation flexibility inverse of weight + attendee count
        flexibility = max(0.0, 1.0 - weight - min(0.3, len(attendees) * 0.05))

        rationale = (
            f"Meeting weight {weight:.2f}: {len(attendees)} attendees, "
            f"{keyword_hits} high-signal keywords"
            f"{', required' if event.get('required') else ''}."
        )
        return ImpactAgentOutput(
            meeting_weight=round(weight, 2),
            attendee_list=attendees,
            cancellation_flexibility=round(flexibility, 2),
            rationale=rationale,
        )
