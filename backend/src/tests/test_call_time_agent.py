import pytest
import os
from unittest.mock import patch
from datetime import datetime, date
from backend.src.travelagent.AmbientOrchestration import AmbientOrchestratorAgent
from backend.src.mcp.tools.flightpydantic import FlightStatusRealtime

@pytest.fixture(autouse=True)
def clean_db():
    # Force the agent to use a completely isolated and temporary test database
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///orchestrator_test_call.db"
    if os.path.exists("orchestrator_test_call.db"):
        try:
            os.remove("orchestrator_test_call.db")
        except Exception:
            pass
    yield
    if os.path.exists("orchestrator_test_call.db"):
        try:
            os.remove("orchestrator_test_call.db")
        except Exception:
            pass

@pytest.mark.asyncio
async def test_call_time_agent_success():
    """Test _call_time_agent with standard mock values yielding high probability."""
    agent = AmbientOrchestratorAgent(
        flight_number      = "2426",
        meeting_id         = "meeting_test_1",
        flight_airlinecode = "AA",
        flight_date        = date(2026, 6, 29),
        scheduled_arrival  = "2026-06-29T17:45:00",
        user_email         = "test@company.com",
    )

    # 1. Create flight status: lands at 18:15:00
    flight_info = FlightStatusRealtime(
        Departure_Airport = "SFO",
        Departure_Time    = datetime.fromisoformat("2026-06-29T12:00:00"),
        Arrival_Airport   = "JFK",
        Arrival_Time      = datetime.fromisoformat("2026-06-29T18:15:00"),
        airline_code      = "AA",
        flight_number     = "2426",
        Status            = "delayed"
    )

    # 2. Mock routing: 45 minute baseline drive
    route_info = {
        "traffic_status": "Heavy",
        "baseline_drive_minutes": 45
    }

    # 3. Mock calendar: meeting starts at 20:30 (plenty of time)
    mock_calendar = {
        "start": "2026-06-29T20:30:00",
        "end": "2026-06-29T21:30:00",
        "attendees": ["guest@company.com"],
        "is_flexible": False
    }

    with patch("backend.src.travelagent.AmbientOrchestration.get_calendar", return_value=mock_calendar):
        res = await agent._call_time_agent(flight_info, route_info)
        
    assert "p_arrive_by_deadline" in res
    p = res["p_arrive_by_deadline"]
    assert isinstance(p, float)
    # Since meeting starts at 20:30, landing is 18:15, terminal is 15 mins, drive is 45 mins, ride buffer is 20 mins.
    # Total arrival time is ~19:35, which leaves plenty of slack. Probability should be high.
    assert p > 0.70


@pytest.mark.asyncio
async def test_call_time_agent_tight_deadline():
    """Test _call_time_agent when landing is too close to meeting start time."""
    agent = AmbientOrchestratorAgent(
        flight_number      = "2426",
        meeting_id         = "meeting_test_2",
        flight_airlinecode = "AA",
        flight_date        = date(2026, 6, 29),
        scheduled_arrival  = "2026-06-29T17:45:00",
        user_email         = "test@company.com",
    )

    # 1. Create flight status: lands at 18:15:00
    flight_info = FlightStatusRealtime(
        Departure_Airport = "SFO",
        Departure_Time    = datetime.fromisoformat("2026-06-29T12:00:00"),
        Arrival_Airport   = "JFK",
        Arrival_Time      = datetime.fromisoformat("2026-06-29T18:15:00"),
        airline_code      = "AA",
        flight_number     = "2426",
        Status            = "delayed"
    )

    # 2. Mock routing: 45 minute baseline drive
    route_info = {
        "traffic_status": "Heavy",
        "baseline_drive_minutes": 45
    }

    # 3. Mock calendar: meeting starts at 18:30 (impossible to arrive on time)
    mock_calendar = {
        "start": "2026-06-29T18:30:00",
        "end": "2026-06-29T19:30:00",
        "attendees": ["guest@company.com"],
        "is_flexible": False
    }

    with patch("backend.src.travelagent.AmbientOrchestration.get_calendar", return_value=mock_calendar):
        res = await agent._call_time_agent(flight_info, route_info)
        
    assert "p_arrive_by_deadline" in res
    p = res["p_arrive_by_deadline"]
    assert isinstance(p, float)
    assert p < 0.30


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__]))
