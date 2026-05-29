"""ImpactAgent subagent — scores meeting importance from calendar metadata.

This mirrors the dev branch folder structure (subagents/ImpactAgent/)
while integrating the companion package's ImpactSignal.

The Impact Agent analyzes calendar event metadata (attendees, keywords,
required flag) to determine how much a missed meeting would matter.

Usage:
    from travelagent.subagents.ImpactAgent.impact_agent import ImpactAgent
    agent = ImpactAgent()
    output = agent.assess(event)
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.src.travelagent.companion.signals.signals import ImpactSignal


@dataclass
class ImpactAgentOutput:
    """Output from the Impact Agent assessment."""
    meeting_weight: float               # in [0, 1]
    attendee_list: list[str]
    cancellation_flexibility: float     # how easy to cancel [0, 1]
    rationale: str

    @property
    def signal(self) -> ImpactSignal:
        return ImpactSignal.from_weight(self.meeting_weight)


class ImpactAgent:
    """Scores the meeting's importance from calendar metadata.

    Considers:
      - Number of attendees (more people = higher weight)
      - High-signal keywords in title/description
      - Whether attendance is marked required

    Signal thresholds:
        LOW:    weight < 0.4
        MEDIUM: 0.4 <= weight < 0.7
        HIGH:   weight >= 0.7

    A board meeting with 10 attendees → HIGH (~0.85)
    A 1:1 catch-up with no keywords → LOW (~0.30)
    """

    HIGH_SIGNAL_KEYWORDS = frozenset({
        "board", "investor", "client", "presentation",
        "critical", "ceo", "interview", "kickoff",
        "all-hands", "quarterly", "demo", "launch",
    })

    def assess(self, event: dict) -> ImpactAgentOutput:
        """Analyze calendar event and return importance weight + signal."""
        attendees = event.get("attendees", [])
        keywords_text = (
            event.get("title", "") + " " + event.get("description", "")
        ).lower()
        keyword_hits = sum(
            1 for kw in self.HIGH_SIGNAL_KEYWORDS if kw in keywords_text
        )

        # Base weight
        weight = 0.2

        # Attendees: each adds 0.05, capped at 0.4
        weight += min(0.4, len(attendees) * 0.05)

        # Keywords: each adds 0.15, capped at 0.4
        weight += min(0.4, keyword_hits * 0.15)

        # Required flag
        if event.get("required"):
            weight += 0.05

        weight = min(weight, 1.0)

        # Cancellation flexibility is inverse of weight + attendee pressure
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