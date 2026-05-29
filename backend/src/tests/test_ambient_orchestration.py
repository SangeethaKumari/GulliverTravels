import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from datetime import date

from backend.src.travelagent.AmbientOrchestration import AmbientOrchestratorAgent

# =====================================================================
# 📊 1. EVALUATION DATASET
# =====================================================================
EVAL_SCENARIOS = [
    {
        "id": "TC_001_happy_path_on_time",
        "description": "On-time flight stays silent.",
        "flight_status_mock": {
            "status": "on_time",
            "departure_airport": "SFO", "arrival_airport": "JFK",
            "departure_time": "2026-06-29T12:00:00",
            "arrival_time":   "2026-06-29T17:45:00",
            "airline_code": "AA", "flight_number": "2426"
        },
        "expected_db_state": {
            "current_status": "on_time",
            "is_monitoring_active": True
        }
    },
    {
        "id": "TC_002_sudden_cancellation_guardrail",
        "description": "Cancelled flight stops the loop immediately.",
        "flight_status_mock": {
            "status": "cancelled",
            "departure_airport": "SFO", "arrival_airport": "JFK",
            "departure_time": "2026-06-29T12:00:00",
            "arrival_time":   "2026-06-29T17:45:00",
            "airline_code": "AA", "flight_number": "2426"
        },
        "expected_db_state": {
            "current_status": "cancelled",
            "is_monitoring_active": False
        }
    },
    {
        "id": "TC_003_standard_minor_delay",
        "description": "30-min delay tracked in history, no email sent.",
        "flight_status_mock": {
            "status": "delayed",
            "departure_airport": "SFO", "arrival_airport": "JFK",
            "departure_time": "2026-06-29T12:00:00",
            "arrival_time":   "2026-06-29T18:15:00",   # +30 min
            "airline_code": "AA", "flight_number": "2426"
        },
        "expected_db_state": {
            "current_status": "delayed",
            "delay_history": [30],
            "is_monitoring_active": True
        }
    },
    {
        "id": "TC_004_critical_delay_breach",
        "description": "90-min delay breaches threshold, email sent.",
        "flight_status_mock": {
            "status": "delayed",
            "departure_airport": "SFO", "arrival_airport": "JFK",
            "departure_time": "2026-06-29T12:00:00",
            "arrival_time":   "2026-06-29T19:15:00",   # +90 min
            "airline_code": "AA", "flight_number": "2426"
        },
        "expected_db_state": {
            "current_status": "delayed",
            "delay_history": [90],
            "is_monitoring_active": True
        }
    },
]


# =====================================================================
# ⚙️ 2. TEST HARNESS
# =====================================================================

import os

@pytest.fixture(autouse=True)
def clean_db():
    # Force the agent to use a completely isolated and temporary test database
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///orchestrator_test.db"
    if os.path.exists("orchestrator_test.db"):
        try:
            os.remove("orchestrator_test.db")
        except Exception:
            pass
    yield
    if os.path.exists("orchestrator_test.db"):
        try:
            os.remove("orchestrator_test.db")
        except Exception:
            pass


# Duck-typed mock event — satisfies _fetch_flight_status's hasattr checks
# without constructing a real ADK Event or google.genai.types.Content
class _MockEvent:
    class _FR:
        def __init__(self, d): self.response = d
    class _Part:
        def __init__(self, d): self.function_response = _MockEvent._FR(d)
    class _Content:
        def __init__(self, d): self.parts = [_MockEvent._Part(d)]
    def __init__(self, d): self.content = _MockEvent._Content(d)


@pytest.mark.parametrize("scenario", EVAL_SCENARIOS, ids=lambda s: s["id"])
@pytest.mark.asyncio
async def test_agent_state_machine_matrix(scenario):
    print(f"\n{scenario['id']} — {scenario['description']}")

    agent = AmbientOrchestratorAgent(
        flight_number      = "2426",
        meeting_id         = f"eval_{scenario['id']}",
        flight_airlinecode = "AA",
        flight_date        = date(2026, 6, 29),
        scheduled_arrival  = "2026-06-29T17:45:00",
        user_email         = "test@company.com",
    )

    async def mock_run_async(runner_self, *args, **kwargs):
        if runner_self.agent.name == "CalendarAgent":
            class _TextPart:
                def __init__(self):
                    self.text = "Mock email sent successfully."
            class _TextContent:
                def __init__(self):
                    self.parts = [_TextPart()]
            class _TextEvent:
                def __init__(self):
                    self.content = _TextContent()
            yield _TextEvent()
        else:
            yield _MockEvent(scenario["flight_status_mock"])

    with patch("google.adk.runners.InMemoryRunner.run_async", new=mock_run_async):
        await agent._sync({"is_monitoring_active": True})
        session = await agent._get_or_init_session()
        await agent._sensing_cycle(session)

    # Re-fetch from DB and assert
    state = (await agent._get_or_init_session()).state
    print(f"DB----------- state: {state}")  # ← add this

    assert state["current_status"] == scenario["expected_db_state"]["current_status"]
    assert state.get("is_monitoring_active", True) == scenario["expected_db_state"]["is_monitoring_active"]

    if "delay_history" in scenario["expected_db_state"]:
        assert state["delay_history"] == scenario["expected_db_state"]["delay_history"]