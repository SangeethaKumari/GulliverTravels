"""TrafficAgent subagent — estimates drive time from airport to meeting venue.

Consults traffic conditions to provide a realistic drive-time estimate
used by the TimeAgent for arrival probability calculations.

Usage:
    from travelagent.subagents.TrafficAgent.traffic_agent import TrafficAgent
    agent = TrafficAgent()
    output = agent.assess(origin, destination, departure_time)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TrafficAgentOutput:
    """Output from the Traffic Agent."""
    drive_minutes: float            # estimated drive time in current conditions
    free_flow_minutes: float        # drive time with no traffic
    traffic_level: str              # "low" | "medium" | "high"
    confidence: float
    rationale: str


class TrafficAgent:
    """Estimates drive time from airport to meeting location.

    In production, this would call a routing API (TomTom, Google Maps, etc.).
    Currently uses the route dict returned by the companion's mock tools.
    """

    def assess(self, route: dict) -> TrafficAgentOutput:
        """Analyze route conditions and return drive time estimate."""
        drive_min = route["durationSeconds"] / 60
        free_flow_min = route["durationInFreeFlowSeconds"] / 60

        # Determine traffic level from congestion ratio
        ratio = drive_min / free_flow_min if free_flow_min > 0 else 1.0
        if ratio < 1.2:
            traffic_level = "low"
        elif ratio < 1.5:
            traffic_level = "medium"
        else:
            traffic_level = "high"

        confidence = 0.90 if traffic_level == "low" else 0.75

        rationale = (
            f"Drive time {drive_min:.0f}m (free flow {free_flow_min:.0f}m), "
            f"traffic level: {traffic_level} (ratio {ratio:.2f}x)."
        )

        return TrafficAgentOutput(
            drive_minutes=round(drive_min, 1),
            free_flow_minutes=round(free_flow_min, 1),
            traffic_level=traffic_level,
            confidence=confidence,
            rationale=rationale,
        )
