"""MCP-style tools for the Ambient Travel Companion.

Each tool is a thin, well-typed wrapper around the mock services in
`mocks.py`. In a production deployment, these would call real APIs
(FlightRadar24, OpenWeatherMap, TomTom, Google Calendar, Uber/Lyft);
the agent code remains identical.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from . import mocks


def get_flight_status(flight_number: str, date: Optional[str] = None) -> dict:
    """Real-time flight status (mocked)."""
    return mocks.mock_flight_status(flight_number)


def get_weather(lat: float, lon: float, forecast_hours: int = 6) -> dict:
    """Current weather + short-term trend at a location (mocked)."""
    return mocks.mock_weather(lat, lon)


def estimate_route(origin: str, destination: str, depart_time: Optional[str] = None) -> dict:
    """Estimated drive time under current traffic (mocked)."""
    return mocks.mock_route(origin, destination, depart_time)


def get_calendar_events(user_id: str) -> list:
    """User's upcoming calendar events (mocked)."""
    return mocks.mock_calendar_events(user_id)


def get_attendee_availability(attendees: list, start: datetime, end: datetime) -> dict:
    """Free/busy lookup across attendees (mocked)."""
    return mocks.mock_freebusy(attendees, start, end)


def book_ride(pickup: tuple, dropoff: tuple, request_time: datetime,
              service: str = "uber") -> dict:
    """Pre-book a rideshare (mocked Uber/Lyft)."""
    return mocks.mock_book_ride(pickup, dropoff, request_time, service)


def cancel_ride(ride_id: str) -> dict:
    """Cancel a previously booked ride (mocked)."""
    return mocks.mock_cancel_ride(ride_id)
