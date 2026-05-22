"""Historical flight calibration and hallucination detection.

Core idea
---------
The TimeAgent computes a probability using a hand-crafted exponential model:

    p_heuristic = 1.0 - 0.5 * exp(-slack_min / 15)

This is our *prior belief* about punctuality, based only on current slack.
It knows nothing about whether UA123 is chronically late or obsessively
on-time.

This module adds a *historical likelihood*:

    p_historical = (on-time flights for this route/flight) / total_flights

We then combine them via Bayesian shrinkage:

    p_calibrated = (n_eff * p_heuristic + n_hist * p_hist) / (n_eff + n_hist)

where n_eff = 10 (the heuristic is worth ~10 data points of confidence).

Hallucination detection
-----------------------
A heuristic is "hallucinating" when it is confidently wrong relative to
history. We test this using the Wilson score confidence interval for
p_historical. If p_heuristic falls *outside* the 95% CI of the historical
estimate, the agent is over/under-confident.

    hallucination_score = max(0, ci_lower - p_heuristic)   # over-optimistic
                        + max(0, p_heuristic - ci_upper)   # over-pessimistic

    is_hallucinating = hallucination_score > 0 (i.e. outside CI)

This gives you a per-decision audit trail: "at 14:23 the heuristic said 0.93
but history says 0.51 (CI 0.38–0.64), hallucination_score=0.29."
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class HistoricalFlight:
    """One historical leg for a given flight number."""
    flight_number: str
    departure_date: datetime        # scheduled departure (UTC)
    scheduled_arrival: datetime     # scheduled arrival (UTC)
    actual_arrival: Optional[datetime]  # None if cancelled/unknown
    status: str                     # "on_time" | "delayed" | "cancelled"
    delay_minutes: int              # 0 if on_time; negative = early

    @property
    def is_on_time(self) -> bool:
        """On-time = arrived within 15 minutes of schedule."""
        if self.status == "cancelled":
            return False
        if self.actual_arrival is None:
            return False
        return self.delay_minutes <= 15


@dataclass
class HistoricalStats:
    """Aggregated stats for a query window."""
    flight_number: str
    n_total: int
    n_on_time: int
    p_historical: float             # empirical on-time rate
    ci_lower: float                 # Wilson 95% CI lower bound
    ci_upper: float                 # Wilson 95% CI upper bound
    avg_delay_minutes: float
    sample_note: str                # human-readable caveat about sample size


@dataclass
class CalibrationResult:
    """Full output of the calibration check for one TimeAgent assessment."""
    p_heuristic: float              # raw value from TimeAgent
    p_historical: float             # empirical from history (or -1 if no data)
    p_calibrated: float             # Bayesian-shrunk final probability
    ci_lower: float
    ci_upper: float
    n_samples: int

    hallucination_score: float      # 0 = fine; >0 = heuristic outside CI
    is_hallucinating: bool          # hallucination_score > 0

    direction: str                  # "over_optimistic" | "over_pessimistic" | "ok"
    rationale: str


# ---------------------------------------------------------------------------
# In-memory flight history store
# ---------------------------------------------------------------------------

class FlightHistoryStore:
    """Stores historical flight records and answers statistical queries.

    In production this would wrap a DB query (e.g. BTS data, airline API).
    For testing and simulation it's populated with seed data.
    """

    def __init__(self):
        self._records: list[HistoricalFlight] = []

    def add(self, record: HistoricalFlight) -> None:
        self._records.append(record)

    def add_many(self, records: list[HistoricalFlight]) -> None:
        self._records.extend(records)

    def query(
        self,
        flight_number: str,
        day_of_week: Optional[int] = None,   # 0=Mon … 6=Sun
        hour_of_day: Optional[int] = None,   # 0–23, ±2h window applied
    ) -> list[HistoricalFlight]:
        """Return matching records, optionally filtered by day/hour."""
        results = [r for r in self._records if r.flight_number == flight_number]

        if day_of_week is not None:
            # Allow ±1 day to widen the sample
            allowed_days = {
                (day_of_week - 1) % 7,
                day_of_week,
                (day_of_week + 1) % 7,
            }
            results = [r for r in results
                       if r.departure_date.weekday() in allowed_days]

        if hour_of_day is not None:
            results = [r for r in results
                       if abs(r.departure_date.hour - hour_of_day) <= 2]

        return results

    def get_stats(
        self,
        flight_number: str,
        day_of_week: Optional[int] = None,
        hour_of_day: Optional[int] = None,
    ) -> HistoricalStats:
        records = self.query(flight_number, day_of_week, hour_of_day)
        n = len(records)

        if n == 0:
            return HistoricalStats(
                flight_number=flight_number,
                n_total=0,
                n_on_time=0,
                p_historical=0.5,   # uninformative prior when no data
                ci_lower=0.0,
                ci_upper=1.0,
                avg_delay_minutes=0.0,
                sample_note="No historical data — using uniform prior.",
            )

        on_time = sum(1 for r in records if r.is_on_time)
        p_hat = on_time / n
        ci_lower, ci_upper = _wilson_ci(on_time, n, z=1.96)

        delays = [r.delay_minutes for r in records if r.status != "cancelled"]
        avg_delay = sum(delays) / len(delays) if delays else 0.0

        if n < 5:
            note = f"Small sample ({n} flights) — CI is wide."
        elif n < 20:
            note = f"Moderate sample ({n} flights)."
        else:
            note = f"Robust sample ({n} flights)."

        return HistoricalStats(
            flight_number=flight_number,
            n_total=n,
            n_on_time=on_time,
            p_historical=round(p_hat, 3),
            ci_lower=round(ci_lower, 3),
            ci_upper=round(ci_upper, 3),
            avg_delay_minutes=round(avg_delay, 1),
            sample_note=note,
        )


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------

# Effective sample weight of the heuristic model.
# "The hand-tuned formula is worth about 10 historical observations."
_N_EFF_HEURISTIC = 10


class HistoricalCalibrator:
    """Combines TimeAgent's heuristic p with empirical flight history.

    Usage
    -----
        store = FlightHistoryStore()
        store.add_many(seed_records("UA123"))
        calibrator = HistoricalCalibrator(store)

        result = calibrator.calibrate(
            flight_number="UA123",
            p_heuristic=0.93,
            departure_dt=datetime(...),
        )
        print(result.p_calibrated, result.is_hallucinating)
    """

    def __init__(self, store: FlightHistoryStore):
        self._store = store

    def calibrate(
        self,
        flight_number: str,
        p_heuristic: float,
        departure_dt: Optional[datetime] = None,
    ) -> CalibrationResult:
        """Return a calibrated probability and hallucination assessment."""
        day = departure_dt.weekday() if departure_dt else None
        hour = departure_dt.hour if departure_dt else None

        stats = self._store.get_stats(flight_number, day_of_week=day,
                                       hour_of_day=hour)
        n_hist = stats.n_total
        p_hist = stats.p_historical
        ci_lower = stats.ci_lower
        ci_upper = stats.ci_upper

        # ── Bayesian shrinkage ──────────────────────────────────────────────
        # p_calibrated is a weighted average: heuristic gets weight n_eff,
        # history gets weight n_hist.  When history is sparse, we stay close
        # to the heuristic; when history is large, we trust it more.
        p_calibrated = (
            (_N_EFF_HEURISTIC * p_heuristic + n_hist * p_hist)
            / (_N_EFF_HEURISTIC + n_hist)
        )
        p_calibrated = round(min(max(p_calibrated, 0.01), 0.99), 3)

        # ── Hallucination detection ─────────────────────────────────────────
        # The heuristic is "hallucinating" if it falls outside the 95% CI of
        # the historical estimate.  No data → CI is (0, 1) → never flags.
        if p_heuristic < ci_lower:
            h_score = round(ci_lower - p_heuristic, 3)
            direction = "over_pessimistic"
        elif p_heuristic > ci_upper:
            h_score = round(p_heuristic - ci_upper, 3)
            direction = "over_optimistic"
        else:
            h_score = 0.0
            direction = "ok"

        is_hallucinating = h_score > 0

        # ── Rationale ──────────────────────────────────────────────────────
        if n_hist == 0:
            rationale = (
                f"No history for {flight_number} — heuristic p={p_heuristic} "
                f"used as-is (p_calibrated={p_calibrated})."
            )
        else:
            rationale = (
                f"{flight_number}: history p={p_hist} "
                f"(n={n_hist}, 95%CI [{ci_lower}–{ci_upper}]), "
                f"heuristic p={p_heuristic}, "
                f"calibrated p={p_calibrated}."
            )
            if is_hallucinating:
                rationale += (
                    f" ⚠ HALLUCINATION ({direction}): heuristic is "
                    f"{h_score:.3f} outside CI — unreliable reasoning."
                )

        return CalibrationResult(
            p_heuristic=p_heuristic,
            p_historical=p_hist,
            p_calibrated=p_calibrated,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            n_samples=n_hist,
            hallucination_score=h_score,
            is_hallucinating=is_hallucinating,
            direction=direction,
            rationale=rationale,
        )


# ---------------------------------------------------------------------------
# Wilson score confidence interval
# ---------------------------------------------------------------------------

def _wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    More accurate than the normal approximation for small n and extreme p.
    Returns (lower, upper).
    """
    if n == 0:
        return 0.0, 1.0
    p_hat = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
    return max(0.0, center - margin), min(1.0, center + margin)


# ---------------------------------------------------------------------------
# Seed data — realistic historical records for common test flights
# ---------------------------------------------------------------------------

def seed_records(flight_number: str) -> list[HistoricalFlight]:
    """Return a realistic synthetic history for well-known test flights.

    Profiles:
      UA123  — chronically delayed (p_on_time ≈ 0.45) — heuristic will over-
               estimate on clear days → hallucination detected
      AA456  — highly reliable    (p_on_time ≈ 0.92) — heuristic and history agree
      DL789  — Friday evening curse (p_on_time Mon-Thu ≈ 0.88, Fri ≈ 0.42)
    """
    from datetime import timezone as tz
    base = datetime(2025, 1, 6, 14, 0, tzinfo=tz.utc)  # Monday

    records: list[HistoricalFlight] = []

    if flight_number == "UA123":
        # 30 flights, only ~9 on-time (delay=0)  → p ≈ 0.30 < 0.60
        # This models a chronically delayed flight — heuristic will be overoptimistic.
        profile = [
            45, 90,  0, 120, 30,  60,  0, 45, 90,  0,
           120, 30,  0,  60, 45,   0, 90, 120, 0, 30,
            60,  0, 45,  90,  0, 120, 30,  0, 60, 45,
        ]
        from datetime import timedelta as _td
        for i, delay in enumerate(profile):
            dep = base + _td(days=i)
            scheduled_arr = dep.replace(hour=16, minute=0)
            status = "on_time" if delay <= 15 else "delayed"
            records.append(HistoricalFlight(
                flight_number="UA123",
                departure_date=dep,
                scheduled_arrival=scheduled_arr,
                actual_arrival=scheduled_arr + _td(minutes=delay),
                status=status,
                delay_minutes=delay,
            ))

    elif flight_number == "AA456":
        # 25 flights, 23 on-time → p ≈ 0.92
        delays = [0, 0, 0, 0, 0, 5, 0, 0, 0, 0,
                  0, 25, 0, 0, 0, 0, 10, 0, 0, 0,
                  0, 0, 0, 0, 0]
        from datetime import timedelta as _td
        for i, delay in enumerate(delays):
            dep = base + _td(days=i)
            scheduled_arr = dep.replace(hour=17, minute=0)
            status = "on_time" if delay <= 15 else "delayed"
            records.append(HistoricalFlight(
                flight_number="AA456",
                departure_date=dep,
                scheduled_arrival=scheduled_arr,
                actual_arrival=scheduled_arr + _td(minutes=delay),
                status=status,
                delay_minutes=delay,
            ))

    elif flight_number == "DL789":
        # 20 flights: Mon-Thu great, Fri terrible
        # weekday() 0=Mon ... 4=Fri
        from datetime import timedelta as _td
        for i in range(20):
            dep = base + _td(days=i)
            dow = dep.weekday()
            delay = 0 if dow < 4 else 95  # Friday curse
            scheduled_arr = dep.replace(hour=18, minute=0)
            status = "on_time" if delay <= 15 else "delayed"
            records.append(HistoricalFlight(
                flight_number="DL789",
                departure_date=dep,
                scheduled_arrival=scheduled_arr,
                actual_arrival=scheduled_arr + _td(minutes=delay),
                status=status,
                delay_minutes=delay,
            ))

    return records
