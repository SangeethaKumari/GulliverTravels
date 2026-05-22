import pytest
import asyncio
from unittest.mock import patch
from datetime import datetime

# Import your agent framework components
from backend.src.travelagent.orchestrationagent import AmbientOrchestratorAgent

# =====================================================================
# 📊 1. THE GOLDEN EVALUATION DATASET
# =====================================================================
EVAL_SCENARIOS = [
    {
        "id": "TC_001_happy_path_on_time",
        "description": "Verify an on-time flight updates state cleanly and remains silent.",
        "flight_status_mock": "**Status:** on_time\n**arrival_time:** 2026-06-29T17:45:00",
        "expected_db_state": {
            "current_status": "on_time",
            "is_monitoring_active": True
        }
    },
    {
        "id": "TC_002_sudden_cancellation_guardrail",
        "description": "Verify a cancelled flight cuts the polling loop immediately and logs a ledger.",
        "flight_status_mock": "**Status:** cancelled\n**arrival_time:** --",
        "expected_db_state": {
            "current_status": "cancelled",
            "is_monitoring_active": False
        }
    },
    {
        "id": "TC_003_standard_minor_delay",
        "description": "Verify a 30-minute delay updates history but stays under the critical alert threshold.",
        "flight_status_mock": "**Status:** delayed\n**arrival_time:** 2026-06-29T18:15:00", # 30 mins late
        "expected_db_state": {
            "current_status": "delayed",
            "delay_history": [30],
            "is_monitoring_active": True
        }
    },
    {
        "id": "TC_004_critical_delay_breach",
        "description": "Verify a 90-minute delay breaches bounds and shuts down the worker tracking state.",
        "flight_status_mock": "**Status:** delayed\n**arrival_time:** 2026-06-29T19:15:00", # 90 mins late
        "expected_db_state": {
            "current_status": "delayed",
            "delay_history": [90],
            # If your brain logic disables tracking on critical breach:
            "is_monitoring_active": False 
        }
    }
]


# =====================================================================
# ⚙️ 2. THE AUTOMATED TESTING HARNESS
# =====================================================================

@pytest.mark.parametrize("scenario", EVAL_SCENARIOS, ids=lambda s: s["id"])
@pytest.mark.asyncio
async def test_agent_state_machine_matrix(scenario):
    """
    Automated evaluation path matrix. Injects mock telemetry layouts and
    asserts against targeted database session schemas.
    """
    print(f"\nEvaluating Validation Vector: {scenario['id']} - {scenario['description']}")

    # 1. Initialize a completely isolated agent instance for this specific row entry
    agent = AmbientOrchestratorAgent(
        flight_number="2426",
        meeting_id=f"eval_sync_{scenario['id']}",
        flight_airlinecode="AA",
        flight_date="20260629"
    )

    # Define the exact import function path we are intercepting
    target_tool_patch = 'backend.src.travelagent.orchestrationagent.flight_status'

    # 2. Intercept the live flight status API connection using context patching
    with patch(target_tool_patch) as mock_flight_tool:
        # Force the backend utility to output our targeted mock layout string
        mock_flight_tool.return_value = scenario["flight_status_mock"]

        # Pull a clean session data proxy structure from SQLite
        session = await agent._get_or_init_session()

        # Execute exactly ONE execution sensing loop cycle
        await agent._execute_sensing_cycle(session)

        # 3. FORENSIC VERIFICATION: Re-fetch the row state directly from SQLite to audit the agent
        updated_session = await agent._get_or_init_session()
        actual_state = updated_session.state

        # --- ASSERTION VALIDATION CHECKS ---
        # A code modification bug that alters these JSON keys will break these rows, stopping the pipeline!
        assert actual_state["current_status"] == scenario["expected_db_state"]["current_status"]
        
        assert actual_state.get("is_monitoring_active", True) == scenario["expected_db_state"]["is_monitoring_active"]

        # Check the historical tracking trace array if the test vector expects it
        if "delay_history" in scenario["expected_db_state"]:
            assert actual_state["delay_history"] == scenario["expected_db_state"]["delay_history"]