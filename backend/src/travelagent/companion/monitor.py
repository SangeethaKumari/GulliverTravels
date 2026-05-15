"""Ambient monitoring loop — the heart of the ambient agent.

`monitor_trip()` runs continuously, polling tools, detecting material
changes, running the committee, and dispatching actions. It persists
all state to SQLite so it survives restarts and supports audit/replay.

For testing, `simulate_timeline()` replays a scripted multi-step
timeline synchronously (no sleep, no async) — ideal for pytest.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import mcp_tools, mocks
from .actions import ActionLog, NotificationService, RideOrchestrator
from .agents import ImpactAgent, RiskAgent, TimeAgent
from .calendar_agent import CalendarAgent
from .change_detector import material_change
from .composer import HeuristicComposer, NotificationContext
from .mocks import ScenarioState
from .persistence import DB
from .signals import Decision, ImpactSignal, RiskSignal, TimeSignal


class AmbientOrchestrator:
    """Orchestrator that runs the continuous monitoring loop."""

    def __init__(self, db: DB, user_name: str = "Sam", composer=None):
        self.db = db
        self.user_name = user_name
        self.time_agent = TimeAgent()
        self.risk_agent = RiskAgent()
        self.impact_agent = ImpactAgent()
        self.calendar_agent = CalendarAgent()
        self.notifier = NotificationService(composer=composer or HeuristicComposer())
        self.rides = RideOrchestrator()

    # ------------------------------------------------------------------
    # Single poll cycle
    # ------------------------------------------------------------------
    def poll_and_assess(self, trip_id: str, flight_number: str,
                        user_id: str) -> dict:
        """Poll all tools, save snapshot, return raw state dict."""
        flight = mcp_tools.get_flight_status(flight_number)
        weather = mcp_tools.get_weather(40.64, -73.78)
        route = mcp_tools.estimate_route("JFK", "Midtown Manhattan")
        events = mcp_tools.get_calendar_events(user_id)

        state = {
            "flight_status": flight["currentStatus"],
            "delay_minutes": flight.get("delayMinutes", 0),
            "delay_trend": flight.get("delayTrend", "stable"),
            "weather_condition": weather["current"]["condition"],
            "weather_trend": weather.get("trend", "stable"),
            "traffic_level": route.get("congestionLevel", "low"),
            "drive_time_min": int(route["durationSeconds"] / 60),
        }

        polled_at = mocks.now()
        snapshot_id = self.db.save_snapshot(
            trip_id=trip_id,
            polled_at=polled_at,
            raw_payload={"flight": flight, "weather": weather,
                         "route": route, "events": events},
            **state,
        )

        return {
            **state,
            "snapshot_id": snapshot_id,
            "flight": flight,
            "weather": weather,
            "route": route,
            "events": events,
            "polled_at": polled_at,
        }

    def run_committee(self, state: dict, trip: dict) -> dict:
        """Run Time/Risk/Impact agents on a state snapshot, return result dict."""
        flight = state["flight"]
        weather = state["weather"]
        route = state["route"]
        events = state["events"]
        event = events[0] if events else {"title": "Unknown", "attendees": [],
                                           "start": trip["deadline"]}
        meeting_start = datetime.fromisoformat(event["start"])

        ride_eta = mocks.current_scenario().ride_eta_minutes

        time_out = self.time_agent.assess(flight, route, ride_eta, meeting_start)
        risk_out = self.risk_agent.assess(flight, weather)
        impact_out = self.impact_agent.assess(event)

        # Adjust probability for risk
        adjusted_p = max(0.0, min(1.0,
            time_out.p_arrive_by_deadline / risk_out.delay_multiplier))

        # Derive signals
        time_sig = TimeSignal.from_probability(adjusted_p)
        risk_sig = risk_out.signal
        impact_sig = impact_out.signal

        # Decision via truth table
        decision = Decision.from_signals(
            time=time_sig, risk=risk_sig, impact=impact_sig,
            flight_cancelled=(flight["currentStatus"] == "cancelled"),
        )

        rationale = (
            f"Time={time_sig.value}(p={adjusted_p:.2f}), "
            f"Risk={risk_sig.value}(x{risk_out.delay_multiplier}), "
            f"Impact={impact_sig.value}(w={impact_out.meeting_weight}) "
            f"→ {decision.value}"
        )

        # Persist
        run_id = self.db.save_committee_run(
            trip_id=trip["trip_id"],
            snapshot_id=state["snapshot_id"],
            time_signal=time_sig.value,
            time_p=round(adjusted_p, 3),
            risk_signal=risk_sig.value,
            risk_multiplier=risk_out.delay_multiplier,
            risk_factors=risk_out.risk_factors,
            impact_signal=impact_sig.value,
            impact_weight=impact_out.meeting_weight,
            decision=decision.value,
            rationale=rationale,
        )

        return {
            "run_id": run_id,
            "decision": decision,
            "time_signal": time_sig,
            "risk_signal": risk_sig,
            "impact_signal": impact_sig,
            "adjusted_p": round(adjusted_p, 3),
            "risk_multiplier": risk_out.delay_multiplier,
            "risk_factors": risk_out.risk_factors,
            "meeting_weight": impact_out.meeting_weight,
            "rationale": rationale,
            "time_output": time_out,
            "risk_output": risk_out,
            "impact_output": impact_out,
            "event": event,
            "meeting_start": meeting_start,
            "flight": flight,
            "weather": weather,
        }

    def dispatch_actions(self, result: dict, trip: dict) -> list[dict]:
        """Execute side-effecting actions based on committee decision."""
        decision = result["decision"]
        event = result["event"]
        meeting_start = result["meeting_start"]
        flight = result["flight"]
        weather = result["weather"]
        log = ActionLog()
        actions = []

        if decision == Decision.SILENT:
            return actions

        # Calendar proposals
        proposed_times = []
        if decision in (Decision.NEGOTIATE, Decision.CANCEL):
            proposed_times = self.calendar_agent.feasible_reschedule_slots(
                meeting_start, event)
            self.db.save_action(result["run_id"], "reschedule_proposed",
                                {"proposals": [t.isoformat() for t in proposed_times]},
                                "sent")
            actions.append({"type": "reschedule_proposed",
                            "proposals": [t.isoformat() for t in proposed_times]})

        # Build notification context
        delay_min = flight.get("delayMinutes", 0) if decision != Decision.CANCEL else 999
        ctx = NotificationContext(
            user_name=self.user_name,
            delay_minutes=delay_min,
            delay_reason=flight.get("delayReason", ""),
            meeting_title=event.get("title", "Meeting"),
            attendees=event.get("attendees", []),
            original_meeting_time=meeting_start,
            proposed_times=proposed_times or [meeting_start + timedelta(days=1)],
            weather_condition=weather["current"]["condition"],
        )

        # Notify user
        if decision in (Decision.HEADS_UP, Decision.NEGOTIATE, Decision.CANCEL):
            notif = self.notifier.send(ctx, channel="user", log=log)
            self.db.save_action(result["run_id"], "notify_user", notif, "sent")
            actions.append({"type": "notify_user", **notif})

        # Notify attendees
        if decision in (Decision.NEGOTIATE, Decision.CANCEL):
            notif = self.notifier.send(ctx, channel="attendees", log=log)
            self.db.save_action(result["run_id"], "notify_attendees", notif, "sent")
            actions.append({"type": "notify_attendees", **notif})

        # Book ride (only NEGOTIATE — for CANCEL the flight isn't happening)
        if decision == Decision.NEGOTIATE:
            landing = datetime.fromisoformat(flight["estimatedLanding"])
            pickup_time = landing + timedelta(minutes=20)
            ride = self.rides.book(pickup_time, event.get("title", "dest"), log)
            self.db.save_action(result["run_id"], "book_ride", ride, "booked")
            actions.append({"type": "book_ride", **ride})

        return actions

    # ------------------------------------------------------------------
    # Synchronous timeline simulation (for testing)
    # ------------------------------------------------------------------
    def simulate_timeline(self, trip_id: str, flight_number: str,
                          user_id: str, timeline_steps: list[dict],
                          base_time: Optional[datetime] = None) -> list[dict]:
        """Replay a scripted timeline, return list of per-step results.
        
        Each step in `timeline_steps` is a dict matching ScenarioState fields
        plus `time_offset_min` and `name`.
        """
        base = base_time or datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)

        # Ensure trip exists
        trip = self.db.get_trip(trip_id)
        if not trip:
            # Use the first step's meeting start as deadline
            first_step = timeline_steps[0]
            deadline = base + timedelta(minutes=240)  # 4h out
            self.db.create_trip(trip_id, user_id, flight_number, deadline)
            trip = self.db.get_trip(trip_id)

        prev_snapshot_state = None
        prev_decision = None
        iteration_results = []

        for i, step in enumerate(timeline_steps):
            offset = step.pop("time_offset_min", i * 5)
            step_name = step.pop("name", f"step_{i+1}")

            # Configure mocks for this step
            scenario = ScenarioState(name=step_name, **step)
            mocks.set_scenario(scenario)
            mocks.set_now(base + timedelta(minutes=offset))

            # Poll
            state = self.poll_and_assess(trip_id, flight_number, user_id)

            # Check for terminal state
            if state["flight_status"] == "landed":
                self.db.end_trip(trip_id, "completed")
                iteration_results.append({
                    "iteration": i + 1,
                    "name": step_name,
                    "polled_at": state["polled_at"].isoformat(),
                    "flight_status": "landed",
                    "decision": "LOOP_END",
                    "actions": [],
                    "material_change": True,
                    "rationale": "Flight landed — loop terminated.",
                })
                break

            # Material change?
            changed = material_change(prev_snapshot_state, state)
            actions = []
            decision_str = prev_decision or "SILENT"
            rationale = "No material change — committee not run."

            if changed:
                result = self.run_committee(state, trip)
                decision = result["decision"]
                decision_str = decision.value
                rationale = result["rationale"]

                # Only dispatch if decision changed
                if decision_str != prev_decision and decision != Decision.SILENT:
                    actions = self.dispatch_actions(result, trip)

                prev_decision = decision_str

            prev_snapshot_state = state
            iteration_results.append({
                "iteration": i + 1,
                "name": step_name,
                "polled_at": state["polled_at"].isoformat(),
                "flight_status": state["flight_status"],
                "delay_minutes": state["delay_minutes"],
                "weather": state["weather_condition"],
                "traffic": state["traffic_level"],
                "decision": decision_str,
                "material_change": changed,
                "actions": [a.get("type", "unknown") for a in actions],
                "rationale": rationale,
            })

        return iteration_results
