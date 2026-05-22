"""CalibratedTimeAgent — wraps TimeAgent with historical calibration.

Drop-in replacement for TimeAgent.assess() that:
  1. Runs the standard heuristic assessment
  2. Queries FlightHistoryStore for empirical on-time rate
  3. Bayesian-shrinks the heuristic toward history
  4. Flags hallucination when heuristic is outside the historical 95% CI
  5. Returns an enriched TimeAgentOutput with calibration attached

Usage
-----
    from travelagent.companion.calibrated_agent import CalibratedTimeAgent
    from travelagent.companion.historical import FlightHistoryStore, seed_records

    store = FlightHistoryStore()
    store.add_many(seed_records("UA123"))

    agent = CalibratedTimeAgent(store)
    output = agent.assess(flight, route, ride_eta_min, meeting_start,
                          flight_number="UA123")

    print(output.p_arrive_by_deadline)   # calibrated probability
    print(output.calibration.is_hallucinating)
    print(output.calibration.rationale)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .historical import FlightHistoryStore, HistoricalCalibrator, CalibrationResult
from .signals import TimeSignal


# ---------------------------------------------------------------------------
# Enriched output dataclass
# ---------------------------------------------------------------------------

@dataclass
class CalibratedTimeAgentOutput:
    """TimeAgentOutput + calibration metadata."""
    # ── Core fields (same as TimeAgentOutput) ─────────────────────────────
    p_arrive_by_deadline: float     # calibrated (Bayesian-shrunk)
    p_heuristic: float              # raw heuristic before history correction
    median_arrival: datetime
    percentile_10: datetime
    percentile_90: datetime
    rationale: str

    # ── Calibration ────────────────────────────────────────────────────────
    calibration: CalibrationResult  # full audit record

    @property
    def signal(self) -> TimeSignal:
        return TimeSignal.from_probability(self.p_arrive_by_deadline)

    @property
    def hallucination_warning(self) -> str:
        """One-liner for logs and dashboards."""
        if not self.calibration.is_hallucinating:
            return ""
        return (
            f"⚠ heuristic={self.p_heuristic:.3f} but history says "
            f"{self.calibration.p_historical:.3f} "
            f"(CI [{self.calibration.ci_lower:.3f}–{self.calibration.ci_upper:.3f}], "
            f"n={self.calibration.n_samples}), "
            f"score={self.calibration.hallucination_score:.3f} [{self.calibration.direction}]"
        )


# ---------------------------------------------------------------------------
# CalibratedTimeAgent
# ---------------------------------------------------------------------------

class CalibratedTimeAgent:
    """TimeAgent with Bayesian correction and hallucination detection.

    The heuristic formula:
        p_heuristic = 1.0 - 0.5 * exp(-slack_min / 15)

    ...only considers current slack.  This agent adjusts that estimate
    using the flight's actual historical on-time record:

        p_calibrated = (N_EFF * p_heuristic + n_hist * p_hist) / (N_EFF + n_hist)

    where N_EFF = 10 (treating the heuristic as 10 virtual observations).

    Hallucination: if p_heuristic falls outside the 95% Wilson CI of the
    historical rate, the reasoning is flagged as unreliable.
    """

    DOMESTIC_TERMINAL_MIN = 15
    INTL_TERMINAL_MIN = 40
    RIDE_BUFFER_MIN = 5

    def __init__(self, history_store: Optional[FlightHistoryStore] = None):
        self._calibrator = (
            HistoricalCalibrator(history_store)
            if history_store else None
        )

    def assess(
        self,
        flight: dict,
        route: dict,
        ride_eta_min: int,
        meeting_start: datetime,
        flight_number: Optional[str] = None,
        international: bool = False,
    ) -> CalibratedTimeAgentOutput:
        # ── 1. Compute heuristic (identical logic to TimeAgent) ────────────
        if flight["currentStatus"] == "cancelled":
            from datetime import timedelta
            p_heuristic = 0.0
            calibration = self._calibrate(flight_number, p_heuristic, None)
            return CalibratedTimeAgentOutput(
                p_arrive_by_deadline=calibration.p_calibrated,
                p_heuristic=p_heuristic,
                median_arrival=meeting_start + timedelta(hours=24),
                percentile_10=meeting_start + timedelta(hours=12),
                percentile_90=meeting_start + timedelta(hours=48),
                rationale="Flight cancelled — arrival not possible by deadline.",
                calibration=calibration,
            )

        from datetime import timedelta

        landing = datetime.fromisoformat(flight["estimatedLanding"])
        terminal = self.INTL_TERMINAL_MIN if international else self.DOMESTIC_TERMINAL_MIN
        ride_wait = ride_eta_min + self.RIDE_BUFFER_MIN
        drive_min = route["durationSeconds"] / 60
        drive_free_min = route["durationInFreeFlowSeconds"] / 60

        median_arrival = landing + timedelta(minutes=terminal + ride_wait + drive_min)
        best_arrival = landing + timedelta(
            minutes=terminal * 0.7 + ride_wait * 0.6 + drive_free_min
        )
        worst_arrival = landing + timedelta(
            minutes=terminal * 1.4 + ride_wait * 1.6 + drive_min * 1.3
        )

        if median_arrival <= meeting_start:
            slack_min = (meeting_start - median_arrival).total_seconds() / 60
            p_heuristic = 1.0 - 0.5 * math.exp(-slack_min / 15.0)
            p_heuristic = min(p_heuristic, 0.98)
        else:
            overshoot_min = (median_arrival - meeting_start).total_seconds() / 60
            p_heuristic = 0.5 * math.exp(-overshoot_min / 20.0)
            p_heuristic = max(p_heuristic, 0.02)

        p_heuristic = round(p_heuristic, 3)

        # ── 2. Calibrate against history ──────────────────────────────────
        calibration = self._calibrate(flight_number, p_heuristic, landing)

        # ── 3. Rationale ──────────────────────────────────────────────────
        rationale = (
            f"Land at {landing.strftime('%H:%M')}, +{terminal}m terminal, "
            f"+{ride_wait}m ride, +{drive_min:.0f}m drive. "
            f"Median arrival {median_arrival.strftime('%H:%M')} vs deadline "
            f"{meeting_start.strftime('%H:%M')}. "
            f"p_heuristic={p_heuristic:.3f} → p_calibrated="
            f"{calibration.p_calibrated:.3f} (n_hist={calibration.n_samples})."
        )

        return CalibratedTimeAgentOutput(
            p_arrive_by_deadline=calibration.p_calibrated,
            p_heuristic=p_heuristic,
            median_arrival=median_arrival,
            percentile_10=best_arrival,
            percentile_90=worst_arrival,
            rationale=rationale,
            calibration=calibration,
        )

    def _calibrate(
        self,
        flight_number: Optional[str],
        p_heuristic: float,
        departure_dt: Optional[datetime],
    ) -> CalibrationResult:
        if self._calibrator is None or flight_number is None:
            # No history available — identity calibration
            from .historical import CalibrationResult
            return CalibrationResult(
                p_heuristic=p_heuristic,
                p_historical=0.5,
                p_calibrated=p_heuristic,
                ci_lower=0.0,
                ci_upper=1.0,
                n_samples=0,
                hallucination_score=0.0,
                is_hallucinating=False,
                direction="ok",
                rationale="No historical data available.",
            )
        return self._calibrator.calibrate(flight_number, p_heuristic, departure_dt)
