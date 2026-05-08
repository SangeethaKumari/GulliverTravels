"""Mock data services for the Ambient Travel Companion.

Each service simulates an external API (FlightRadar24, OpenWeatherMap,
TomTom, Google Calendar, Uber/Lyft). The mocks are scenario-driven:
calling `set_scenario("B")` configures the global state so all subsequent
tool calls return deterministic, scenario-appropriate responses.

This lets us exercise the full agent pipeline without live APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Scenario configuration
# ---------------------------------------------------------------------------

@dataclass
class ScenarioState:
    name: str
    # Flight
    flight_status: str = "on_time"  # on_time | delayed | cancelled
    delay_minutes: int = 0
    delay_trend: str = "stable"  # stable | increasing
    delay_reason: str = ""
    # Weather at destination
    weather_condition: str = "clear"  # clear | rain | snow
    weather_trend: str = "stable"  # stable | worsening
    # Traffic
    traffic_level: str = "low"  # low | medium | high
    drive_time_minutes: int = 22
    # Meeting
    meeting_title: str = "Project Sync"
    meeting_attendees: list = field(default_factory=lambda: ["alex@example.com"])
    meeting_keywords: list = field(default_factory=list)
    # Ride
    ride_eta_minutes: int = 8


_state: ScenarioState = ScenarioState(name="DEFAULT")
_now: datetime = datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc)


def set_scenario(state: ScenarioState) -> None:
    global _state
    _state = state


def set_now(now: datetime) -> None:
    global _now
    _now = now


def now() -> datetime:
    return _now


def current_scenario() -> ScenarioState:
    return _state


# ---------------------------------------------------------------------------
# Mock APIs (called by MCP tools)
# ---------------------------------------------------------------------------

def mock_flight_status(flight_number: str) -> dict:
    s = _state
    scheduled_landing = _now + timedelta(minutes=120)
    estimated_landing = scheduled_landing + timedelta(minutes=s.delay_minutes)
    return {
        "flightNumber": flight_number,
        "currentStatus": s.flight_status,
        "scheduledLanding": scheduled_landing.isoformat(),
        "estimatedLanding": estimated_landing.isoformat(),
        "delayMinutes": s.delay_minutes,
        "delayReason": s.delay_reason,
        "delayTrend": s.delay_trend,
        "equipment": "B737-800",
    }


def mock_weather(lat: float, lon: float) -> dict:
    s = _state
    return {
        "lat": lat,
        "lon": lon,
        "current": {
            "condition": s.weather_condition,
            "temperature": 18,
            "visibility": 10 if s.weather_condition == "clear" else 4,
        },
        "trend": s.weather_trend,
    }


def mock_route(origin: str, destination: str, depart_iso: Optional[str] = None) -> dict:
    s = _state
    free_flow = 18
    return {
        "origin": origin,
        "destination": destination,
        "durationSeconds": s.drive_time_minutes * 60,
        "durationInFreeFlowSeconds": free_flow * 60,
        "congestionLevel": s.traffic_level,
        "distanceKm": 24,
    }


def mock_calendar_events(user_id: str) -> list:
    s = _state
    meeting_start = _now + timedelta(minutes=240)  # 4h out
    return [
        {
            "id": "evt-001",
            "title": s.meeting_title,
            "start": meeting_start.isoformat(),
            "duration_minutes": 60,
            "attendees": s.meeting_attendees,
            "description": " ".join(s.meeting_keywords),
            "required": True,
        }
    ]


def mock_freebusy(attendees: list, start: datetime, end: datetime) -> dict:
    # Pretend everyone is free for a 30-min slot starting 30 min after `start`
    return {
        "available_slots": [
            {"start": (start + timedelta(minutes=30)).isoformat(),
             "end": (start + timedelta(minutes=90)).isoformat()},
            {"start": (start + timedelta(minutes=90)).isoformat(),
             "end": (start + timedelta(minutes=150)).isoformat()},
        ],
        "attendees": attendees,
    }


def mock_book_ride(pickup: tuple, dropoff: tuple, request_time: datetime, service: str = "uber") -> dict:
    s = _state
    return {
        "rideId": f"{service}-{int(request_time.timestamp())}",
        "service": service,
        "driverName": "Maria",
        "vehicleModel": "Toyota Prius",
        "plate": "7XK-421",
        "etaMinutes": s.ride_eta_minutes,
        "estimatedFareUSD": 38.50,
        "pickupTime": (request_time + timedelta(minutes=s.ride_eta_minutes)).isoformat(),
    }


def mock_cancel_ride(ride_id: str) -> dict:
    return {"rideId": ride_id, "status": "cancelled"}
