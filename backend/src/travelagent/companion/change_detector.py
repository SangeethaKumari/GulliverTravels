"""Material-change detection between consecutive state snapshots.

A "material change" is a shift significant enough to warrant re-running
the committee. Cheap to evaluate — runs on every poll tick; committee
only fires when this returns True.
"""

from __future__ import annotations

from typing import Optional


def material_change(prev: Optional[dict], curr: dict) -> bool:
    """Return True if the state shift between two snapshots is significant."""
    if prev is None:
        return True  # first poll, always run

    # Flight status changed category
    if prev.get("flight_status") != curr.get("flight_status"):
        return True

    # Delay increased or decreased by >= 15 minutes
    prev_delay = prev.get("delay_minutes", 0) or 0
    curr_delay = curr.get("delay_minutes", 0) or 0
    if abs(curr_delay - prev_delay) >= 15:
        return True

    # Delay trend changed
    if prev.get("delay_trend") != curr.get("delay_trend"):
        return True

    # Weather condition changed category
    if prev.get("weather_condition") != curr.get("weather_condition"):
        return True

    # Weather trend changed
    if prev.get("weather_trend") != curr.get("weather_trend"):
        return True

    # Traffic level stepped up or down
    if prev.get("traffic_level") != curr.get("traffic_level"):
        return True

    # Drive time changed by >= 10 minutes
    prev_drive = prev.get("drive_time_min", 0) or 0
    curr_drive = curr.get("drive_time_min", 0) or 0
    if abs(curr_drive - prev_drive) >= 10:
        return True

    return False
