"""TimeAgent subagent — estimates P(arrive at meeting by deadline).

This mirrors the dev branch folder structure (subagents/TimeAgent/)
while integrating the companion package's signals and calibration.

Two modes:
  1. Heuristic-only (fast, deterministic) — uses exponential slack model
  2. Calibrated (recommended) — adds Bayesian correction via flight history

Usage:
    from travelagent.subagents.TimeAgent.time_agent import TimeAgent
    agent = TimeAgent()
    output = agent.assess(flight, route, ride_eta_min, meeting_start)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from travelagent.companion.signals import TimeSignal
from travelagent.companion.historical import (
    FlightHistoryStore,
    HistoricalCalibrator,
    CalibrationResult,
)


@dataclass
class TimeAgentOutput:
    """Output from the Time Agent assessment."""
    p_arrive_by_deadline: float     # final probability (calibrated if history available)
    p_heuristic: float              # raw heuristic before calibration
    median_arrival: datetime
    percentile_10: datetime         # best case
    percentile_90: datetime         # worst case
    rationale: str
    calibration: Optional[CalibrationResult] = None  # None if no history store

    @property
    def signal(self) -> TimeSignal:
        return TimeSignal.from_probability(self.p_arrive_by_deadline)

    @property
    def is_hallucinating(self) -> bool:
        return self.calibration.is_hallucinating if self.calibration else False

    @property
    def hallucination_warning(self) -> str:
        if not self.calibration or not self.calibration.is_hallucinating:
            return ""
        c = self.calibration
        return (
            f"⚠ heuristic={self.p_heuristic:.3f} but history says "
            f"{c.p_historical:.3f} (CI [{c.ci_lower:.3f}–{c.ci_upper:.3f}], "
            f"n={c.n_samples}), score={c.hallucination_score:.3f} "
            f"[{c.direction}]"
        )


class TimeAgent:
    """Estimates P(arrive at meeting by deadline).

    Heuristic formula:
        if slack >= 0:  p = 1.0 - 0.5 * exp(-slack_min / 15)
        if slack <  0:  p = 0.5 * exp(-overshoot_min / 20)

    With optional historical calibration via Bayesian shrinkage:
        p_calibrated = (N_EFF * p_heuristic + n_hist * p_hist) / (N_EFF + n_hist)

    Hallucination detection:
        Flags when p_heuristic falls outside the 95% Wilson CI of flight history.
    """

    DOMESTIC_TERMINAL_MIN = 15
    INTL_TERMINAL_MIN = 40
    RIDE_BUFFER_MIN = 5

    def __init__(self, history_store: Optional[FlightHistoryStore] = None):
        self._calibrator = (
            HistoricalCalibrator(history_store) if history_store else None
        )

    def assess(
        self,
        flight: dict,
        route: dict,
        ride_eta_min: int,
        meeting_start: datetime,
        flight_number: Optional[str] = None,
        international: bool = False,
    ) -> TimeAgentOutput:
        """Run assessment and return probability + signal + calibration."""

        # ── Cancelled flight ──────────────────────────────────────────────
        if flight["currentStatus"] == "cancelled":
            p_heuristic = 0.0
            cal = self._calibrate(flight_number, p_heuristic, None)
            return TimeAgentOutput(
                p_arrive_by_deadline=cal.p_calibrated if cal else p_heuristic,
                p_heuristic=p_heuristic,
                median_arrival=meeting_start + timedelta(hours=24),
                percentile_10=meeting_start + timedelta(hours=12),
                percentile_90=meeting_start + timedelta(hours=48),
                rationale="Flight cancelled — arrival not possible by deadline.",
                calibration=cal,
            )

        # ── Compute timeline ──────────────────────────────────────────────
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

        # ── Heuristic probability (exponential slack model) ───────────────
        if median_arrival <= meeting_start:
            slack_min = (meeting_start - median_arrival).total_seconds() / 60
            p_heuristic = 1.0 - 0.5 * math.exp(-slack_min / 15.0)
            p_heuristic = min(p_heuristic, 0.98)
        else:
            overshoot_min = (median_arrival - meeting_start).total_seconds() / 60
            p_heuristic = 0.5 * math.exp(-overshoot_min / 20.0)
            p_heuristic = max(p_heuristic, 0.02)

        p_heuristic = round(p_heuristic, 3)

        # ── Historical calibration ────────────────────────────────────────
        cal = self._calibrate(flight_number, p_heuristic, landing)
        p_final = cal.p_calibrated if cal else p_heuristic

        # ── Rationale ─────────────────────────────────────────────────────
        rationale = (
            f"Land at {landing.strftime('%H:%M')}, +{terminal}m terminal, "
            f"+{ride_wait}m ride, +{drive_min:.0f}m drive. "
            f"Median arrival {median_arrival.strftime('%H:%M')} vs deadline "
            f"{meeting_start.strftime('%H:%M')}. "
            f"p_heuristic={p_heuristic:.3f}"
        )
        if cal and cal.n_samples > 0:
            rationale += f" → p_calibrated={cal.p_calibrated:.3f} (n={cal.n_samples})"

        return TimeAgentOutput(
            p_arrive_by_deadline=p_final,
            p_heuristic=p_heuristic,
            median_arrival=median_arrival,
            percentile_10=best_arrival,
            percentile_90=worst_arrival,
            rationale=rationale,
            calibration=cal,
        )

    def _calibrate(
        self,
        flight_number: Optional[str],
        p_heuristic: float,
        departure_dt: Optional[datetime],
    ) -> Optional[CalibrationResult]:
        """Calibrate against history. Returns None if no store configured."""
        if self._calibrator is None or flight_number is None:
            return None
        return self._calibrator.calibrate(flight_number, p_heuristic, departure_dt)
