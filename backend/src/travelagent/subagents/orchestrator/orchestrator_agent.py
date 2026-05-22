"""Orchestrator — runs the committee of subagents and decides action.

This mirrors the dev branch folder structure (subagents/orchestrator/)
while using the companion package's Decision truth table.

The orchestrator:
  1. Calls FlightAgent → get flight status
  2. Calls TrafficAgent → get drive time
  3. Calls TimeAgent → compute P(on_time) with optional historical calibration
  4. Calls RiskAgent → compute delay multiplier
  5. Calls ImpactAgent → compute meeting importance
  6. Applies Decision.from_signals() truth table
  7. Returns a full committee result with rationale + hallucination flag

Usage:
    from travelagent.subagents.orchestrator.orchestrator_agent import Orchestrator
    orch = Orchestrator(history_store=store)
    result = orch.run(flight_data, route_data, weather_data, event_data,
                      meeting_start, flight_number="UA123")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from travelagent.companion.signals import TimeSignal, RiskSignal, ImpactSignal, Decision
from travelagent.companion.historical import FlightHistoryStore
from travelagent.subagents.TimeAgent.time_agent import TimeAgent, TimeAgentOutput
from travelagent.subagents.RiskAgent.risk_agent import RiskAgent, RiskAgentOutput
from travelagent.subagents.ImpactAgent.impact_agent import ImpactAgent, ImpactAgentOutput
from travelagent.subagents.TrafficAgent.traffic_agent import TrafficAgent, TrafficAgentOutput
from travelagent.subagents.FlightAgent.agent import FlightAgent, FlightStatus


@dataclass
class CommitteeResult:
    """Full output from the orchestrator's committee run."""
    decision: Decision
    time_output: TimeAgentOutput
    risk_output: RiskAgentOutput
    impact_output: ImpactAgentOutput
    traffic_output: TrafficAgentOutput
    flight_status: FlightStatus

    time_signal: TimeSignal
    risk_signal: RiskSignal
    impact_signal: ImpactSignal

    is_hallucinating: bool
    hallucination_warning: str
    rationale: str


class Orchestrator:
    """Runs all subagents and applies the truth-table decision policy.

    Integrates:
      - TimeAgent (with optional historical calibration + hallucination detection)
      - RiskAgent (weather/delay volatility assessment)
      - ImpactAgent (meeting importance scoring)
      - TrafficAgent (drive time estimation)
      - FlightAgent (flight status parsing)
      - Decision truth table from companion.signals
    """

    def __init__(self, history_store: Optional[FlightHistoryStore] = None):
        self.time_agent = TimeAgent(history_store=history_store)
        self.risk_agent = RiskAgent()
        self.impact_agent = ImpactAgent()
        self.traffic_agent = TrafficAgent()
        self.flight_agent = FlightAgent()

    def run(
        self,
        flight_data: dict,
        route_data: dict,
        weather_data: dict,
        event_data: dict,
        meeting_start: datetime,
        flight_number: Optional[str] = None,
        ride_eta_min: int = 5,
        international: bool = False,
    ) -> CommitteeResult:
        """Execute the full committee and return a decision."""

        # 1. Flight status
        flight_status = self.flight_agent.get_status(flight_data)

        # 2. Traffic
        traffic_output = self.traffic_agent.assess(route_data)

        # 3. Time assessment (with calibration if history available)
        time_output = self.time_agent.assess(
            flight=flight_data,
            route=route_data,
            ride_eta_min=ride_eta_min,
            meeting_start=meeting_start,
            flight_number=flight_number,
            international=international,
        )

        # 4. Risk assessment
        risk_output = self.risk_agent.assess(flight_data, weather_data)

        # 5. Impact assessment
        impact_output = self.impact_agent.assess(event_data)

        # 6. Extract signals
        time_signal = time_output.signal
        risk_signal = risk_output.signal
        impact_signal = impact_output.signal

        # 7. Truth-table decision
        flight_cancelled = flight_status.current_status == "cancelled"
        flight_diverted = flight_status.current_status == "diverted"

        decision = Decision.from_signals(
            time=time_signal,
            risk=risk_signal,
            impact=impact_signal,
            flight_cancelled=flight_cancelled,
            flight_diverted=flight_diverted,
        )

        # 8. Hallucination check
        is_hallucinating = time_output.is_hallucinating
        hallucination_warning = time_output.hallucination_warning

        # 9. Compose rationale
        rationale = (
            f"Time={time_signal.value}(p={time_output.p_arrive_by_deadline:.2f}), "
            f"Risk={risk_signal.value}(x{risk_output.delay_multiplier:.2f}), "
            f"Impact={impact_signal.value}(w={impact_output.meeting_weight:.2f}) "
            f"→ {decision.value}"
        )
        if is_hallucinating:
            rationale += f" [⚠ HALLUCINATING: {hallucination_warning}]"

        return CommitteeResult(
            decision=decision,
            time_output=time_output,
            risk_output=risk_output,
            impact_output=impact_output,
            traffic_output=traffic_output,
            flight_status=flight_status,
            time_signal=time_signal,
            risk_signal=risk_signal,
            impact_signal=impact_signal,
            is_hallucinating=is_hallucinating,
            hallucination_warning=hallucination_warning,
            rationale=rationale,
        )
