"""RiskAgent subagent — adjusts time estimate by reasoning about volatility.

This mirrors the dev branch folder structure (subagents/RiskAgent/)
while integrating the companion package's RiskSignal.

The Risk Agent identifies compounding risk factors (weather deterioration,
increasing delay trend, adverse conditions) and produces a delay multiplier
that captures how much worse the situation could get.

Usage:
    from travelagent.subagents.RiskAgent.risk_agent import RiskAgent
    agent = RiskAgent()
    output = agent.assess(flight, weather)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from travelagent.companion.signals import RiskSignal


@dataclass
class RiskAgentOutput:
    """Output from the Risk Agent assessment."""
    delay_multiplier: float     # in [1.0, 2.0]
    risk_factors: list[str]
    confidence: float           # how sure we are about the multiplier
    rationale: str

    @property
    def signal(self) -> RiskSignal:
        return RiskSignal.from_multiplier(self.delay_multiplier, self.risk_factors)


class RiskAgent:
    """Adjusts the time estimate by reasoning about volatility.

    Examines weather trends, flight delay patterns, and adverse conditions
    to produce a multiplier in [1.0, 2.0] that represents how much worse
    the actual delay could be compared to the current estimate.

    Signal thresholds:
        LOW:    multiplier < 1.15, no severe factors
        MEDIUM: multiplier < 1.35
        HIGH:   multiplier >= 1.35 or severe factor present

    Severe factors (auto-escalate to HIGH):
        thunderstorm, blizzard, ground_stop,
        adverse_weather_snow, cascading_delays
    """

    def assess(self, flight: dict, weather: dict) -> RiskAgentOutput:
        """Analyze risk factors and return a delay multiplier + signal."""
        factors: list[str] = []
        multiplier = 1.0

        # Weather trend worsening
        if weather.get("trend") == "worsening":
            factors.append("weather_worsening")
            multiplier += 0.15

        # Adverse current conditions
        condition = weather.get("current", {}).get("condition", "clear")
        if condition in ("rain", "snow", "thunderstorm", "blizzard"):
            factors.append(f"adverse_weather_{condition}")
            multiplier += 0.10
            if condition in ("thunderstorm", "blizzard"):
                multiplier += 0.15  # extra penalty for severe

        # Flight delay trend
        if flight.get("delayTrend") == "increasing":
            factors.append("delay_trend_up")
            multiplier += 0.20

        # Already significantly delayed
        if flight.get("delayMinutes", 0) > 60:
            factors.append("significant_delay")
            multiplier += 0.05

        # Ground stop (from flight status or separate field)
        if flight.get("groundStop", False):
            factors.append("ground_stop")
            multiplier += 0.20

        # Cap at 2.0
        multiplier = min(multiplier, 2.0)

        # Confidence decreases with more compounding factors
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
