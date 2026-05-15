"""Calendar agent with business-hours awareness.

Handles the Friday-after-5 → Monday case, weekend filtering,
and attendee time-zone considerations (simplified to single TZ for now).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from . import mcp_tools


class CalendarAgent:
    """Proposes reschedule slots that respect business hours."""

    BIZ_START = 9   # 9 AM
    BIZ_END = 18    # 6 PM

    def feasible_reschedule_slots(self, original_start: datetime,
                                  event: dict) -> list[datetime]:
        """Return up to 3 valid reschedule times."""
        raw_candidates = [
            original_start + timedelta(minutes=30),
            original_start + timedelta(minutes=90),
            original_start + timedelta(hours=3),
            original_start + timedelta(days=1),
        ]

        slots = []
        for c in raw_candidates:
            adjusted = self._snap_to_business_hours(c)
            if adjusted not in slots and adjusted > original_start:
                slots.append(adjusted)
            if len(slots) >= 3:
                break

        # Guarantee at least one slot (next business day 10 AM)
        if not slots:
            slots.append(self._next_business_day(original_start, hour=10))

        return slots

    def _snap_to_business_hours(self, when: datetime) -> datetime:
        """Push a datetime into the next valid business window."""
        # Weekend → Monday 9 AM
        if when.weekday() >= 5:
            return self._next_business_day(when, hour=self.BIZ_START)

        # Friday after BIZ_END → Monday 9 AM
        if when.weekday() == 4 and when.hour >= self.BIZ_END:
            return self._next_business_day(when, hour=self.BIZ_START)

        # Before business hours → same day BIZ_START
        if when.hour < self.BIZ_START:
            return when.replace(hour=self.BIZ_START, minute=0, second=0, microsecond=0)

        # After business hours on Mon-Thu → next day BIZ_START
        if when.hour >= self.BIZ_END:
            next_day = when + timedelta(days=1)
            return self._snap_to_business_hours(
                next_day.replace(hour=self.BIZ_START, minute=0, second=0, microsecond=0)
            )

        return when

    def _next_business_day(self, after: datetime, hour: int = 9) -> datetime:
        """Find the next Monday–Friday after the given datetime."""
        d = after + timedelta(days=1)
        d = d.replace(hour=hour, minute=0, second=0, microsecond=0)
        while d.weekday() >= 5:  # skip Sat/Sun
            d += timedelta(days=1)
        return d

    def get_attendee_availability(self, attendees: list,
                                   start: datetime, end: datetime) -> dict:
        """Delegate to MCP tool for freebusy lookup."""
        return mcp_tools.get_attendee_availability(attendees, start, end)
