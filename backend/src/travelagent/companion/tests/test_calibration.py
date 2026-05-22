"""Tests for historical calibration and hallucination detection.

Run with:
    cd C:\\Users\\SNagral\\GulliverTravels
    $env:PYTHONPATH="backend/src"
    python -m pytest backend/src/travelagent/companion/tests/test_calibration.py -v
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import pytest

from travelagent.companion.historical import (
    HistoricalFlight,
    FlightHistoryStore,
    HistoricalCalibrator,
    HistoricalStats,
    _wilson_ci,
    seed_records,
)
from travelagent.companion.calibrated_agent import CalibratedTimeAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTC = timezone.utc

def _dt(hour: int, minute: int = 0, day: int = 6, month: int = 1, year: int = 2026,
        weekday_override: int | None = None) -> datetime:
    """Jan 6 2026 is a Tuesday (weekday=1)."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _flight_stub(
    status: str = "on_time",
    delay_min: int = 0,
    landing_hour: int = 14,
    landing_min: int = 0,
) -> dict:
    landing = _dt(landing_hour, landing_min)
    return {
        "currentStatus": status,
        "estimatedLanding": landing.isoformat(),
        "delayMinutes": delay_min,
        "delayTrend": "stable",
    }


def _route_stub(drive_min: int = 30) -> dict:
    return {
        "durationSeconds": drive_min * 60,
        "durationInFreeFlowSeconds": int(drive_min * 0.8 * 60),
    }


# ---------------------------------------------------------------------------
# Wilson CI
# ---------------------------------------------------------------------------

class TestWilsonCI:
    def test_zero_samples_returns_full_interval(self):
        lo, hi = _wilson_ci(0, 0)
        assert lo == 0.0 and hi == 1.0

    def test_all_successes_ci_high(self):
        lo, hi = _wilson_ci(20, 20)
        assert lo > 0.8 and hi == 1.0

    def test_no_successes_ci_low(self):
        lo, hi = _wilson_ci(0, 20)
        assert lo == 0.0 and hi < 0.2

    def test_half_successes_centered(self):
        lo, hi = _wilson_ci(10, 20)
        center = (lo + hi) / 2
        assert abs(center - 0.5) < 0.05

    def test_bounds_within_zero_one(self):
        for k in range(0, 31, 5):
            lo, hi = _wilson_ci(k, 30)
            assert 0.0 <= lo <= hi <= 1.0


# ---------------------------------------------------------------------------
# FlightHistoryStore + HistoricalStats
# ---------------------------------------------------------------------------

class TestFlightHistoryStore:
    def setup_method(self):
        self.store = FlightHistoryStore()

    def test_empty_store_returns_uniform_prior(self):
        stats = self.store.get_stats("ZZ999")
        assert stats.n_total == 0
        assert stats.p_historical == 0.5
        assert stats.ci_lower == 0.0 and stats.ci_upper == 1.0

    def test_ua123_chronic_delays(self):
        """UA123 seed data has ~43% on-time rate."""
        self.store.add_many(seed_records("UA123"))
        stats = self.store.get_stats("UA123")
        assert stats.n_total == 30
        assert stats.p_historical < 0.60, (
            f"UA123 should be chronically late, got p={stats.p_historical}"
        )

    def test_aa456_reliable(self):
        """AA456 seed data has ~92% on-time rate."""
        self.store.add_many(seed_records("AA456"))
        stats = self.store.get_stats("AA456")
        assert stats.p_historical > 0.80

    def test_dl789_friday_curse(self):
        """DL789: Mon-Thu fine, Friday ≥ 95 min delay."""
        self.store.add_many(seed_records("DL789"))
        # Query for Friday (weekday=4) explicitly
        fri_stats = self.store.get_stats("DL789", day_of_week=4)
        mon_stats = self.store.get_stats("DL789", day_of_week=0)
        assert fri_stats.p_historical < mon_stats.p_historical, (
            f"Friday p={fri_stats.p_historical} should be < Monday p={mon_stats.p_historical}"
        )

    def test_day_of_week_filter_narrows_sample(self):
        self.store.add_many(seed_records("UA123"))
        all_stats = self.store.get_stats("UA123")
        day_stats = self.store.get_stats("UA123", day_of_week=0)
        assert day_stats.n_total <= all_stats.n_total

    def test_unknown_flight_returns_uniform_prior(self):
        self.store.add_many(seed_records("UA123"))
        stats = self.store.get_stats("XX999")
        assert stats.p_historical == 0.5


# ---------------------------------------------------------------------------
# HistoricalCalibrator — Bayesian shrinkage
# ---------------------------------------------------------------------------

class TestHistoricalCalibrator:
    def setup_method(self):
        self.store = FlightHistoryStore()
        self.store.add_many(seed_records("UA123"))  # chronically late ~0.43
        self.store.add_many(seed_records("AA456"))  # reliable ~0.92
        self.calibrator = HistoricalCalibrator(self.store)

    def test_calibrated_p_between_heuristic_and_historical(self):
        """Bayesian shrinkage pulls calibrated p toward history."""
        result = self.calibrator.calibrate("UA123", p_heuristic=0.93)
        # p_hist ≈ 0.43, heuristic=0.93 → calibrated should be between them
        assert result.p_heuristic > result.p_calibrated
        assert result.p_calibrated > result.p_historical

    def test_calibrated_p_reliable_flight_stays_high(self):
        """AA456 is reliable; heuristic 0.93 and history ~0.92 → still high."""
        result = self.calibrator.calibrate("AA456", p_heuristic=0.93)
        assert result.p_calibrated > 0.88

    def test_no_history_identity_calibration(self):
        result = self.calibrator.calibrate("ZZ999", p_heuristic=0.75)
        # n=0 → p_calibrated == p_heuristic (n_eff / (n_eff + 0) = 1.0)
        assert result.p_calibrated == result.p_heuristic
        assert result.n_samples == 0

    def test_calibrated_p_bounded(self):
        """Calibrated probability must stay in [0.01, 0.99]."""
        result_low = self.calibrator.calibrate("UA123", p_heuristic=0.01)
        result_high = self.calibrator.calibrate("AA456", p_heuristic=0.99)
        assert 0.01 <= result_low.p_calibrated <= 0.99
        assert 0.01 <= result_high.p_calibrated <= 0.99

    def test_large_history_dominates_heuristic(self):
        """With 30 samples, history should pull calibrated p significantly."""
        result = self.calibrator.calibrate("UA123", p_heuristic=0.93)
        # n_eff=10, n_hist=30 → history weight 75%
        expected = (10 * 0.93 + 30 * result.p_historical) / (10 + 30)
        assert abs(result.p_calibrated - round(expected, 3)) < 0.01


# ---------------------------------------------------------------------------
# Hallucination detection
# ---------------------------------------------------------------------------

class TestHallucinationDetection:
    def setup_method(self):
        self.store = FlightHistoryStore()
        self.store.add_many(seed_records("UA123"))  # p_hist ≈ 0.43
        self.store.add_many(seed_records("AA456"))  # p_hist ≈ 0.92
        self.calibrator = HistoricalCalibrator(self.store)

    def test_over_optimistic_hallucination_detected(self):
        """Heuristic 0.95 on a chronically-late flight → over-optimistic."""
        result = self.calibrator.calibrate("UA123", p_heuristic=0.95)
        assert result.is_hallucinating
        assert result.direction == "over_optimistic"
        assert result.hallucination_score > 0

    def test_over_pessimistic_hallucination_detected(self):
        """Heuristic 0.10 on a reliable flight → over-pessimistic."""
        result = self.calibrator.calibrate("AA456", p_heuristic=0.10)
        assert result.is_hallucinating
        assert result.direction == "over_pessimistic"

    def test_no_hallucination_when_heuristic_within_ci(self):
        """Heuristic 0.92 on reliable AA456 (CI ≈ [0.75–0.98]) → ok."""
        result = self.calibrator.calibrate("AA456", p_heuristic=0.92)
        assert not result.is_hallucinating
        assert result.direction == "ok"
        assert result.hallucination_score == 0.0

    def test_no_hallucination_when_no_history(self):
        """Unknown flight: CI is (0, 1), heuristic always inside → never flags."""
        result = self.calibrator.calibrate("ZZ999", p_heuristic=0.99)
        assert not result.is_hallucinating

    def test_hallucination_score_proportional_to_deviation(self):
        """Larger deviation from CI should produce higher score."""
        r1 = self.calibrator.calibrate("UA123", p_heuristic=0.75)  # mildly outside
        r2 = self.calibrator.calibrate("UA123", p_heuristic=0.95)  # far outside
        if r1.is_hallucinating and r2.is_hallucinating:
            assert r2.hallucination_score > r1.hallucination_score

    def test_rationale_contains_warning_when_hallucinating(self):
        result = self.calibrator.calibrate("UA123", p_heuristic=0.95)
        assert "HALLUCINATION" in result.rationale


# ---------------------------------------------------------------------------
# CalibratedTimeAgent end-to-end
# ---------------------------------------------------------------------------

class TestCalibratedTimeAgent:
    def setup_method(self):
        self.store = FlightHistoryStore()
        self.store.add_many(seed_records("UA123"))
        self.store.add_many(seed_records("AA456"))
        self.agent = CalibratedTimeAgent(self.store)

    def test_reliable_flight_comfortable_buffer_stays_green(self):
        """AA456 + 90min buffer: heuristic ≈ 0.97, history ≈ 0.92 → GREEN."""
        meeting = _dt(17, 30)   # 17:30
        flight = _flight_stub(landing_hour=15, landing_min=0)  # land 15:00
        # 15:00 + 15m terminal + 5m ride + 30m drive → 15:50 → 90 min slack
        route = _route_stub(drive_min=30)
        out = self.agent.assess(flight, route, ride_eta_min=0,
                                meeting_start=meeting, flight_number="AA456")
        from travelagent.companion.signals import TimeSignal
        assert out.signal == TimeSignal.GREEN
        assert not out.calibration.is_hallucinating

    def test_chronic_delay_flight_gets_downgraded(self):
        """UA123 with ample slack: heuristic says GREEN but history pulls it down."""
        meeting = _dt(17, 30)
        flight = _flight_stub(landing_hour=15, landing_min=0)
        route = _route_stub(drive_min=30)
        out = self.agent.assess(flight, route, ride_eta_min=0,
                                meeting_start=meeting, flight_number="UA123")
        # Calibrated p should be lower than the raw heuristic
        assert out.p_arrive_by_deadline < out.p_heuristic

    def test_ua123_clear_day_hallucination_flagged(self):
        """On a clear day UA123 heuristic ≈ 0.97 but history says ~0.43 → flag."""
        meeting = _dt(17, 30)
        flight = _flight_stub(landing_hour=15, landing_min=0)
        route = _route_stub(drive_min=30)
        out = self.agent.assess(flight, route, ride_eta_min=0,
                                meeting_start=meeting, flight_number="UA123")
        assert out.calibration.is_hallucinating
        assert out.hallucination_warning != ""

    def test_cancelled_flight_calibration_still_attached(self):
        """Cancelled flight gets CalibrationResult even when p_heuristic=0."""
        meeting = _dt(17, 30)
        flight = {"currentStatus": "cancelled", "estimatedLanding": _dt(15).isoformat(),
                  "delayMinutes": 999, "delayTrend": "stable"}
        route = _route_stub()
        out = self.agent.assess(flight, route, ride_eta_min=0,
                                meeting_start=meeting, flight_number="UA123")
        assert out.p_heuristic == 0.0
        assert out.calibration is not None

    def test_no_history_store_no_hallucination(self):
        """Without a store, the agent is identity-calibrated — never flags."""
        agent = CalibratedTimeAgent(history_store=None)
        meeting = _dt(17, 30)
        flight = _flight_stub(landing_hour=15, landing_min=0)
        out = agent.assess(flight, _route_stub(), ride_eta_min=0,
                           meeting_start=meeting)
        assert not out.calibration.is_hallucinating
        assert out.p_arrive_by_deadline == out.p_heuristic

    def test_output_has_signal_property(self):
        meeting = _dt(17, 30)
        flight = _flight_stub(landing_hour=15, landing_min=0)
        out = self.agent.assess(flight, _route_stub(), ride_eta_min=0,
                                meeting_start=meeting, flight_number="AA456")
        from travelagent.companion.signals import TimeSignal
        assert isinstance(out.signal, TimeSignal)
