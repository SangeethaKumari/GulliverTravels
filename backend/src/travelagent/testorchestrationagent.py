import asyncio
from unittest.mock import patch
from backend.src.travelagent.orchestrationagent import AmbientOrchestratorAgent

# --- 1. DEFINE MOCK SCENARIOS ---
MOCK_SCENARIOS = {
    "on_time": """**Flights Status Results ':**
 **departure_airport:** SFO
   **departure_time:** 2026-06-29T08:30:00
   **arrival_airport:** JFK
   **arrival_time:** 2026-06-29T16:45:00
   **airline:** AA
   **flight_nubmer:** 2426
   **Status:** on_time""",

    "delayed": """**Flights Status Results ':**
 **departure_airport:** SFO
   **departure_time:** 2026-06-29T08:30:00
   **arrival_airport:** JFK
   **arrival_time:** 2026-06-29T18:15:00
   **airline:** AA
   **flight_nubmer:** 2426
   **Status:** delayed""",

    "cancelled": """**Flights Status Results ':**
 **departure_airport:** SFO
   **departure_time:** 2026-06-29T08:30:00
   **arrival_airport:** JFK
   **arrival_time:** --
   **airline:** AA
   **flight_nubmer:** 2426
   **Status:** cancelled"""
}

# --- 2. THE TEST EXECUTION ENGINE ---
async def execute_single_test_run(scenario_name: str, mock_string_data: str):
    print(f"\n=======================================================")
    print(f"🚀 RUNNING SIMULATION SCENARIO: [{scenario_name.upper()}]")
    print(f"=======================================================")
    
    # Initialize a clean agent instance for this scenario
    # We alter the meeting_id so each scenario gets its own clean row in SQLite
    agent = AmbientOrchestratorAgent(
        flight_number="2426",
        meeting_id=f"meet_test_{scenario_name}",
        flight_airlinecode="AA",
        flight_date="20260629"
    )
    
    # We patch the specific flight_status import inside the orchestrationagent context
    target_patch = 'backend.src.travelagent.orchestrationagent.flight_status'
    with patch(target_patch) as mock_flight_tool:
        # Force the tool to return this specific scenario's string layout
        mock_flight_tool.return_value = mock_string_data
        
        # Initialize the session and execute exactly ONE sensing cycle
        session = await agent._get_or_init_session()
        #await agent._execute_session_flight_status(session)
        await agent._execute_sensing_cycle(session)

MOCK_TIMELINE = {
    "cycle_1": """**Flights Status Results ':**
   **arrival_time:** 2026-06-29T18:15:00
   **Status:** delayed""",  # 30-minute delay

    "cycle_2": """**Flights Status Results ':**
   **arrival_time:** 2026-06-29T18:45:00
   **Status:** delayed""",  # 60-minute delay

    "cycle_3": """**Flights Status Results ':**
   **arrival_time:** 2026-06-29T19:15:00
   **Status:** delayed"""   # 90-minute delay (Critical Breach!)
}

async def simulate_cascading_delay():
    # Use a fixed meeting ID so it targets the same row instead of creating new ones
    agent = AmbientOrchestratorAgent(
        flight_number="2426",
        meeting_id="meet_cascade_test",
        flight_airlinecode="AA",
        flight_date="20260629"
    )
    
    target_patch = 'backend.src.travelagent.orchestrationagent.flight_status'
    
    # Run through the timeline sequence step-by-step
    for cycle_name, mock_string_data in MOCK_TIMELINE.items():
        print(f"\n🔄 Executing: {cycle_name}")
        
        with patch(target_patch) as mock_flight_tool:
            mock_flight_tool.return_value = mock_string_data
            
            # Fetch the session (loads previous history from SQLite)
            session = await agent._get_or_init_session()
            
            # Execute the sensing cycle to parse, calculate, and append
            await agent._execute_sensing_cycle(session)


# --- 3. MAIN INTERFACE TRIGGER ---
def main():
    # CHOOSE YOUR TEST METHOD:
    
    # Option A: Run ONE specific scenario at a time (Comment out if you want to run all)
    # asyncio.run(execute_single_test_run("delayed", MOCK_SCENARIOS["delayed"]))
    
    # Option B: Run ALL scenarios sequentially to check every code path at once
    #for status, mock_data in MOCK_SCENARIOS.items():
        #asyncio.run(execute_single_test_run(status, mock_data))
    # Option C: Run the CASCADING delay simulation
    asyncio.run(simulate_cascading_delay())

if __name__ == "__main__":
    main()