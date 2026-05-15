"""Tests for the ambient monitoring loop, signals, persistence, and timelines."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from travelagent.companion.signals import (Decision, ImpactSignal, RiskSignal,
                                            TimeSignal)
from travelagent.companion.change_detector import material_change
from travelagent.companion.persistence import DB
from travelagent.companion.monitor import AmbientOrchestrator
from travelagent.companion.composer import HeuristicComposer
from travelagent.companion.calendar_agent import CalendarAgent
from travelagent.companion.timelines import (timeline_storm_at_iteration_7,
                                              timeline_friday_evening,
                                              timeline_cancellation_recovery,
                                              timeline_landed)
import copy


# ── Signal tests ──────────────────────────────────────

class TestSignals:
    def test_time_signal_boundaries(self):
        assert TimeSignal.from_probability(0.90) == TimeSignal.GREEN
        assert TimeSignal.from_probability(0.85) == TimeSignal.GREEN
        assert TimeSignal.from_probability(0.84) == TimeSignal.YELLOW
        assert TimeSignal.from_probability(0.60) == TimeSignal.YELLOW
        assert TimeSignal.from_probability(0.59) == TimeSignal.RED
        assert TimeSignal.from_probability(0.0) == TimeSignal.RED

    def test_risk_signal_severe_factor(self):
        assert RiskSignal.from_multiplier(1.0, ["thunderstorm"]) == RiskSignal.HIGH
        assert RiskSignal.from_multiplier(1.0, []) == RiskSignal.LOW
        assert RiskSignal.from_multiplier(1.20, []) == RiskSignal.MEDIUM
        assert RiskSignal.from_multiplier(1.40, []) == RiskSignal.HIGH

    def test_impact_signal_boundaries(self):
        assert ImpactSignal.from_weight(0.3) == ImpactSignal.LOW
        assert ImpactSignal.from_weight(0.5) == ImpactSignal.MEDIUM
        assert ImpactSignal.from_weight(0.7) == ImpactSignal.HIGH
        assert ImpactSignal.from_weight(1.0) == ImpactSignal.HIGH

    def test_decision_truth_table(self):
        # GREEN + LOW + any → SILENT
        assert Decision.from_signals(TimeSignal.GREEN, RiskSignal.LOW,
                                      ImpactSignal.HIGH) == Decision.SILENT
        # RED → NEGOTIATE regardless
        assert Decision.from_signals(TimeSignal.RED, RiskSignal.LOW,
                                      ImpactSignal.LOW) == Decision.NEGOTIATE
        # YELLOW + HIGH impact → NEGOTIATE
        assert Decision.from_signals(TimeSignal.YELLOW, RiskSignal.LOW,
                                      ImpactSignal.HIGH) == Decision.NEGOTIATE
        # YELLOW + MEDIUM impact → HEADS_UP
        assert Decision.from_signals(TimeSignal.YELLOW, RiskSignal.LOW,
                                      ImpactSignal.MEDIUM) == Decision.HEADS_UP
        # Cancelled overrides everything
        assert Decision.from_signals(TimeSignal.GREEN, RiskSignal.LOW,
                                      ImpactSignal.LOW,
                                      flight_cancelled=True) == Decision.CANCEL


# ── Change detector tests ─────────────────────────────

class TestChangeDetector:
    def test_first_poll_is_always_change(self):
        assert material_change(None, {"flight_status": "on_time"}) is True

    def test_no_change(self):
        s = {"flight_status": "on_time", "delay_minutes": 10,
             "delay_trend": "stable", "weather_condition": "clear",
             "weather_trend": "stable", "traffic_level": "low",
             "drive_time_min": 22}
        assert material_change(s, s.copy()) is False

    def test_flight_status_change(self):
        prev = {"flight_status": "on_time", "delay_minutes": 0}
        curr = {"flight_status": "delayed", "delay_minutes": 0}
        assert material_change(prev, curr) is True

    def test_delay_increase_15min(self):
        prev = {"flight_status": "delayed", "delay_minutes": 20}
        curr = {"flight_status": "delayed", "delay_minutes": 35}
        assert material_change(prev, curr) is True

    def test_delay_increase_under_15min(self):
        prev = {"flight_status": "delayed", "delay_minutes": 20,
                "delay_trend": "stable", "weather_condition": "clear",
                "weather_trend": "stable", "traffic_level": "low",
                "drive_time_min": 22}
        curr = {**prev, "delay_minutes": 30}
        assert material_change(prev, curr) is False

    def test_weather_change(self):
        prev = {"weather_condition": "clear"}
        curr = {"weather_condition": "rain"}
        assert material_change(prev, curr) is True


# ── Persistence tests ─────────────────────────────────

class TestPersistence:
    def test_trip_lifecycle(self):
        db = DB(":memory:")
        db.create_trip("t1", "u1", "UA123",
                       datetime(2026, 5, 14, 16, 0, tzinfo=timezone.utc))
        trip = db.get_trip("t1")
        assert trip["status"] == "active"

        db.end_trip("t1", "completed")
        trip = db.get_trip("t1")
        assert trip["status"] == "completed"
        db.close()

    def test_snapshot_and_retrieval(self):
        db = DB(":memory:")
        db.create_trip("t1", "u1", "UA123",
                       datetime(2026, 5, 14, 16, 0, tzinfo=timezone.utc))
        sid = db.save_snapshot("t1", datetime.now(timezone.utc),
                               "delayed", 30, "increasing",
                               "rain", "worsening", "high", 45, {})
        assert sid > 0
        latest = db.get_latest_snapshot("t1")
        assert latest["delay_minutes"] == 30
        db.close()


# ── Calendar agent tests ──────────────────────────────

class TestCalendarAgent:
    def test_friday_after_5_pushes_to_monday(self):
        cal = CalendarAgent()
        # Friday 5:30 PM UTC
        friday = datetime(2026, 5, 15, 17, 30, tzinfo=timezone.utc)
        slots = cal.feasible_reschedule_slots(friday, {"attendees": []})
        # All slots should be Monday or later
        for s in slots:
            assert s.weekday() < 5, f"Got weekend slot: {s}"
            assert s >= friday

    def test_weekend_pushes_to_monday(self):
        cal = CalendarAgent()
        saturday = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        slots = cal.feasible_reschedule_slots(saturday, {"attendees": []})
        for s in slots:
            assert s.weekday() < 5

    def test_normal_weekday_keeps_same_day(self):
        cal = CalendarAgent()
        tuesday_2pm = datetime(2026, 5, 12, 14, 0, tzinfo=timezone.utc)
        slots = cal.feasible_reschedule_slots(tuesday_2pm, {"attendees": []})
        assert len(slots) >= 1
        # First slot should be same day (30 min later)
        assert slots[0].date() == tuesday_2pm.date()


# ── Timeline simulation tests ─────────────────────────

class TestTimelines:
    def _run(self, timeline_factory):
        steps = [copy.deepcopy(s) for s in timeline_factory()]
        db = DB(":memory:")
        orch = AmbientOrchestrator(db=db, user_name="Sam",
                                    composer=HeuristicComposer())
        results = orch.simulate_timeline(
            trip_id="test-trip",
            flight_number="UA123",
            user_id="user-1",
            timeline_steps=steps,
        )
        db.close()
        return results

    def test_storm_timeline_decisions(self):
        results = self._run(timeline_storm_at_iteration_7)
        decisions = [r["decision"] for r in results]
        # First 6 should be SILENT (calm conditions, green)
        for d in decisions[:6]:
            assert d == "SILENT", f"Expected SILENT in calm phase, got {d}"
        # Step 7 or 8 should escalate
        assert any(d in ("HEADS_UP", "NEGOTIATE") for d in decisions[6:]), \
            f"Expected escalation after storm, got {decisions[6:]}"

    def test_storm_material_changes(self):
        results = self._run(timeline_storm_at_iteration_7)
        # Iteration 1 always has material change (first poll)
        assert results[0]["material_change"] is True
        # Iterations 2-6 should NOT have material changes (nothing changed)
        for r in results[1:6]:
            assert r["material_change"] is False, \
                f"Unexpected change at {r['name']}"
        # Iteration 7 should have material change (storm hits)
        assert results[6]["material_change"] is True

    def test_cancellation_stops_re_running(self):
        results = self._run(timeline_cancellation_recovery)
        decisions = [r["decision"] for r in results]
        assert decisions[0] == "SILENT"  # on time
        assert decisions[1] == "CANCEL"  # cancelled
        # Step 3: no material change → committee not re-run → stays CANCEL
        assert results[2]["material_change"] is False

    def test_landed_terminates_loop(self):
        results = self._run(timeline_landed)
        assert results[-1]["decision"] == "LOOP_END"
        assert results[-1]["flight_status"] == "landed"

    def test_persistence_audit_trail(self):
        steps = [copy.deepcopy(s) for s in timeline_storm_at_iteration_7()]
        db = DB(":memory:")
        orch = AmbientOrchestrator(db=db, user_name="Sam",
                                    composer=HeuristicComposer())
        orch.simulate_timeline("audit-trip", "UA123", "user-1", steps)

        # Should have 8 snapshots (one per poll)
        snaps = db.get_snapshots("audit-trip")
        assert len(snaps) == 8

        # Committee runs only when material change occurred
        runs = db.get_committee_runs("audit-trip")
        # At minimum: iteration 1 (first) + iteration 7 (storm) + iteration 8
        assert len(runs) >= 3

        # Actions only after escalation
        actions = db.get_actions("audit-trip")
        assert len(actions) >= 1  # at least one notification
        db.close()
