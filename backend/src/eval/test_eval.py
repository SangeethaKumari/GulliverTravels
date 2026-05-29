"""Basic evaluation for Financial Advisor"""

import pathlib

import dotenv
import pytest
from google.adk.evaluation.agent_evaluator import AgentEvaluator

pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session", autouse=True)
def load_env():
    dotenv.load_dotenv()


@pytest.mark.asyncio
async def test_all():
    """Test the agent's basic ability on a few examples."""
    print("Running evaluate")
    await AgentEvaluator.evaluate(
        "ambient_travel_companion",
        str(pathlib.Path(__file__).parent / "data"),
        num_runs=5,
    )

   # 1. Safely extract values from 'raw', supporting both Title_Case and snake_case variants
                        #dep_air = raw.get("departure_airport") or raw.get("Departure_Airport") or ""
                        #arr_air = raw.get("arrival_airport") or raw.get("Arrival_Airport") or ""
                        #dep_time_str = raw.get("departure_time") or raw.get("Departure_Time") or ""
                        #arr_time_str = raw.get("arrival_time") or raw.get("Arrival_Time") or ""
                        #airline = raw.get("airline_code") or raw.get("airline_code") or ""
                        #flight_num = raw.get("flight_number") or raw.get("flight_number") or ""
                        #status_val = raw.get("status") or raw.get("Status") or ""
