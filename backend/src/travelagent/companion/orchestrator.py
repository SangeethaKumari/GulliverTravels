"""Orchestrator: synthesizes the committee's outputs into a decision and
dispatches the appropriate action sequence.

Decision policy from the brief (pp. 55–56):

  * P(on time) > 0.85 and meeting weight < 0.5  → SILENT
  * P in [0.60, 0.85) and weight > 0.5           → HEADS_UP
  * P < 0.60 or (delay > 90m and weight > 0.7)   → NEGOTIATE
  * Flight cancelled                             → CANCEL
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from . import mcp_tools, mocks
from .actions import (ActionLog, CalendarNegotiator, NotificationService,
                      RideOrchestrator)
from .agents import (ImpactAgent, ImpactAgentOutput, RiskAgent,
                     RiskAgentOutput, TimeAgent, TimeAgentOutput)
from .composer import NotificationContext, HeuristicComposer


DECISION_SILENT = "SILENT"
DECISION_HEADS_UP = "HEADS_UP"
DECISION_NEGOTIATE = "NEGOTIATE"
DECISION_CANCEL = "CANCEL"


@dataclass
class DecisionRecord:
    decision: str
    p_on_time: float
    adjusted_p_on_time: float
    meeting_weight: float
    risk_multiplier: float
    rationale: str
    time_output: TimeAgentOutput
    risk_output: RiskAgentOutput
    impact_output: ImpactAgentOutput


@dataclass
class RunResult:
    scenario: str
    decision: DecisionRecord
    log: ActionLog = field(default_factory=ActionLog)


class Orchestrator:
    def __init__(self, user_name: str = "Sam", composer=None):
        self.user_name = user_name
        self.time_agent = TimeAgent()
        self.risk_agent = RiskAgent()
        self.impact_agent = ImpactAgent()
        self.notifier = NotificationService(composer=composer or HeuristicComposer())
        self.negotiator = CalendarNegotiator()
        self.rides = RideOrchestrator()

    # ------------------------------------------------------------------
    def run_cycle(self, flight_number: str = "UA123",
                  user_id: str = "user-1") -> RunResult:
        log = ActionLog()

        # 1. Pull data via MCP tools
        flight = mcp_tools.get_flight_status(flight_number)
        weather = mcp_tools.get_weather(40.64, -73.78)  # JFK
        route = mcp_tools.estimate_route("JFK", "Midtown Manhattan")
        events = mcp_tools.get_calendar_events(user_id)
        event = events[0]
        meeting_start = datetime.fromisoformat(event["start"])

        # 2. Run committee
        ride_eta = mocks.current_scenario().ride_eta_minutes
        time_out = self.time_agent.assess(flight, route, ride_eta, meeting_start)
        risk_out = self.risk_agent.assess(flight, weather)
        impact_out = self.impact_agent.assess(event)

        adjusted_p = max(0.0, min(1.0, time_out.p_arrive_by_deadline / risk_out.delay_multiplier))

        # 3. Decide
        decision, rationale = self._decide(
            flight=flight,
            time_out=time_out,
            risk_out=risk_out,
            impact_out=impact_out,
            adjusted_p=adjusted_p,
        )

        record = DecisionRecord(
            decision=decision,
            p_on_time=time_out.p_arrive_by_deadline,
            adjusted_p_on_time=round(adjusted_p, 3),
            meeting_weight=impact_out.meeting_weight,
            risk_multiplier=risk_out.delay_multiplier,
            rationale=rationale,
            time_output=time_out,
            risk_output=risk_out,
            impact_output=impact_out,
        )

        # 4. Act
        self._dispatch(decision, event, meeting_start, flight, weather, log)

        return RunResult(scenario=mocks.current_scenario().name,
                         decision=record, log=log)

    # ------------------------------------------------------------------
    def _decide(self, flight, time_out, risk_out, impact_out, adjusted_p):
        if flight["currentStatus"] == "cancelled":
            return DECISION_CANCEL, "Flight cancelled — must reschedule meeting."
        weight = impact_out.meeting_weight
        delay = flight.get("delayMinutes", 0)

        if adjusted_p >= 0.85 and weight < 0.5:
            return DECISION_SILENT, "High arrival probability and low-weight meeting."
        if adjusted_p < 0.60 or (delay > 90 and weight > 0.7):
            return DECISION_NEGOTIATE, (
                f"Adjusted P(on time)={adjusted_p:.2f}, delay={delay}m, "
                f"weight={weight:.2f} — proactive reschedule warranted."
            )
        if 0.60 <= adjusted_p < 0.85 and weight > 0.5:
            return DECISION_HEADS_UP, (
                f"Tight but not critical: P={adjusted_p:.2f}, weight={weight:.2f}."
            )
        return DECISION_SILENT, "Conditions within normal bounds."

    # ------------------------------------------------------------------
    def _dispatch(self, decision, event, meeting_start, flight, weather, log):
        if decision == DECISION_SILENT:
            return

        if decision == DECISION_CANCEL:
            ctx = self._build_ctx(
                delay_minutes=999,
                delay_reason="flight cancelled",
                event=event,
                meeting_start=meeting_start,
                proposed_times=[meeting_start + timedelta(days=1)],
                weather=weather,
            )
            self.notifier.send(ctx, channel="attendees", log=log)
            self.negotiator.propose_reschedule(event, meeting_start, log)
            # If a ride was previously booked we'd cancel it here.
            return

        # HEADS_UP and NEGOTIATE both compose messages; NEGOTIATE also
        # books the ride and proposes calendar updates.
        proposed_times = self.negotiator.propose_reschedule(event, meeting_start, log) \
            if decision == DECISION_NEGOTIATE else [meeting_start]

        ctx = self._build_ctx(
            delay_minutes=flight.get("delayMinutes", 0),
            delay_reason=flight.get("delayReason", ""),
            event=event,
            meeting_start=meeting_start,
            proposed_times=proposed_times,
            weather=weather,
        )

        if decision == DECISION_HEADS_UP:
            self.notifier.send(ctx, channel="user", log=log)
            return

        # DECISION_NEGOTIATE
        self.notifier.send(ctx, channel="user", log=log)
        self.notifier.send(ctx, channel="attendees", log=log)
        # Pre-book ride for slightly after estimated landing + terminal clearance
        landing = datetime.fromisoformat(flight["estimatedLanding"])
        pickup_time = landing + timedelta(minutes=20)
        self.rides.book(pickup_time, dropoff_address=event["title"], log=log)

    # ------------------------------------------------------------------
    def _build_ctx(self, delay_minutes, delay_reason, event, meeting_start,
                   proposed_times, weather) -> NotificationContext:
        return NotificationContext(
            user_name=self.user_name,
            delay_minutes=delay_minutes,
            delay_reason=delay_reason,
            meeting_title=event["title"],
            attendees=event["attendees"],
            original_meeting_time=meeting_start,
            proposed_times=proposed_times,
            weather_condition=weather["current"]["condition"],
        )
