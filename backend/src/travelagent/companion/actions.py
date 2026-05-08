"""Action layer: notification, calendar negotiation, ride booking.

These are the side-effecting subsystems the orchestrator dispatches to
once it decides intervention is warranted. Side effects here are
recorded in the action log rather than actually sent / booked, so the
test harness can inspect everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from . import mcp_tools
from .composer import NotificationContext, HeuristicComposer, composite_reward


@dataclass
class ActionLog:
    notifications: list = field(default_factory=list)
    calendar_updates: list = field(default_factory=list)
    rides_booked: list = field(default_factory=list)
    rides_cancelled: list = field(default_factory=list)


class NotificationService:
    def __init__(self, composer=None):
        self.composer = composer or HeuristicComposer()

    def send(self, ctx: NotificationContext, channel: str, log: ActionLog) -> dict:
        message = self.composer.compose(ctx)
        rewards = composite_reward(message, ctx)
        record = {
            "channel": channel,
            "to": ctx.attendees if channel != "user" else ["user"],
            "message": message,
            "rewards": rewards,
        }
        log.notifications.append(record)
        return record


class CalendarNegotiator:
    def propose_reschedule(self, event: dict, original_start: datetime,
                           log: ActionLog) -> list:
        """Find 3 candidate slots and emit calendar update proposals."""
        attendees = event.get("attendees", [])
        availability = mcp_tools.get_attendee_availability(
            attendees, original_start, original_start + timedelta(hours=8)
        )
        # Three options: defer 30m, defer 90m, next day same time
        proposals = [
            original_start + timedelta(minutes=30),
            original_start + timedelta(minutes=90),
            original_start + timedelta(days=1),
        ]
        update = {
            "event_id": event["id"],
            "original_start": original_start.isoformat(),
            "proposals": [t.isoformat() for t in proposals],
            "free_slots": availability["available_slots"],
        }
        log.calendar_updates.append(update)
        return proposals


class RideOrchestrator:
    def book(self, pickup_time: datetime, dropoff_address: str,
             log: ActionLog, service: str = "uber") -> dict:
        ride = mcp_tools.book_ride(
            pickup=("airport", "TERMINAL_3"),
            dropoff=("destination", dropoff_address),
            request_time=pickup_time,
            service=service,
        )
        log.rides_booked.append(ride)
        return ride

    def cancel(self, ride_id: str, log: ActionLog) -> dict:
        result = mcp_tools.cancel_ride(ride_id)
        log.rides_cancelled.append(result)
        return result
