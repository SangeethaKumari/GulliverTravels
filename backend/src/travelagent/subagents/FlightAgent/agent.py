"""FlightAgent subagent — retrieves and interprets flight status.

Provides flight data (status, delay, estimated landing) that feeds
into the TimeAgent and RiskAgent assessments.

Usage:
    from travelagent.subagents.FlightAgent.agent import FlightAgent
    agent = FlightAgent()
    status = agent.get_status("UA123")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FlightStatus:
    """Structured flight status output."""
    flight_number: str
    current_status: str          # "on_time" | "delayed" | "cancelled" | "in_air" | "landed"
    delay_minutes: int
    delay_trend: str             # "stable" | "increasing" | "decreasing"
    estimated_landing: Optional[datetime]
    gate: Optional[str]
    rationale: str


class FlightAgent:
    """Retrieves and interprets current flight status.

    In production, wraps an airline status API (FlightAware, AeroAPI, etc.).
    For testing, accepts pre-built flight dicts from the companion mocks.
    """

    def get_status(self, flight_data: dict) -> FlightStatus:
        """Parse a flight data dict into structured FlightStatus."""
        landing_str = flight_data.get("estimatedLanding")
        landing = (
            datetime.fromisoformat(landing_str) if landing_str else None
        )

        status = flight_data.get("currentStatus", "unknown")
        delay = flight_data.get("delayMinutes", 0)
        trend = flight_data.get("delayTrend", "stable")
        gate = flight_data.get("gate")
        flight_number = flight_data.get("flightNumber", "unknown")

        rationale = (
            f"{flight_number}: status={status}, delay={delay}m "
            f"(trend: {trend})"
        )
        if landing:
            rationale += f", landing at {landing.strftime('%H:%M')}"

        return FlightStatus(
            flight_number=flight_number,
            current_status=status,
            delay_minutes=delay,
            delay_trend=trend,
            estimated_landing=landing,
            gate=gate,
            rationale=rationale,
        )
