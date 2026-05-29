# Ambient Orchestrator Agent: Architecture & Flow

This document explains the core architecture, execution flow, and design logic of the `AmbientOrchestratorAgent`. It is designed to act as a stateful, background supervisor that continuously monitors travel conditions and orchestrates specialized sub-agents to make automated, risk-adjusted decisions.

---

## 1. Core Architecture

The Orchestrator is built using an **Event-Driven Sense-Think-Act** architecture powered by the Google ADK.

*   **Stateful Persistence (ADK Sessions):** Unlike a stateless script, the Orchestrator maintains an ongoing "memory" of a flight's status. It connects to an SQLite database (`orchestrator_state.db`) via the `DatabaseSessionService`. Every time the flight status updates, it commits an `Event` payload to the database, ensuring that if the server crashes, the agent remembers its delay history and loop state.
*   **Ambient Loop (Background Worker):** The agent spins up an asynchronous while-loop (`_main_loop_worker`) that wakes up periodically (e.g., every 30 seconds for testing, 5 minutes in production) to perform a factual check of the real world.
*   **Tool-Enabled (FastMCP):** It relies on external API tools (Flight Status, Weather, Traffic Route, Calendar) to perceive the environment.

---

## 2. The Execution Flow (Sense-Think-Act)

Every time the loop wakes up, it executes a single **Sensing Cycle** (`_execute_sensing_cycle`).

### Phase A: PERCEIVE (Factual Check)
The agent calls the `flight_status` tool to get the real-time textual data of the flight. It parses this string to extract the `Status` and the `arrival_time`.

*   **Gatekeeper Rules:** To save compute costs (LLM tokens and API calls), the agent uses deterministic branching right at the start:
    *   **If `CANCELLED`**: It immediately emits a cancellation decision, shuts down its monitoring loop, and exits.
    *   **If `ON_TIME`**: It commits the safe state to the database and goes back to sleep silently. 
    *   **If `DELAYED`**: It proceeds to Phase B to gather more context.

### Phase B: GATHER EXTRA CONTEXT (The Committee)
Once a delay is verified, the agent pulls additional environmental streams that might compound the delay:
*   **Weather:** (`get_weather`) Checks conditions at the destination.
*   **Traffic:** (`estimate_route`) Checks live drive times from the airport to the meeting.
*   **Calendar:** (`get_calendar`) Checks how important/flexible the upcoming meeting is.

### Phase C: THINK & COMPUTE (Delegation & Risk Adjustment)
The Orchestrator distributes this rich context to specialized sub-agents (currently mocked as worker functions):
1.  **Time Agent:** Evaluates route and flight info to calculate the probability of arriving on time (`p_arrive_by_deadline`).
2.  **Risk Agent:** Looks at weather and historical delays to generate a penalty (`delay_multiplier`).
3.  **Impact Agent:** Evaluates the calendar to determine the `meeting_weight`.

**The Math:** 
The Orchestrator executes a strict mathematical boundary check: 
`adjusted_p = max(0.0, p - (0.2 * (mult - 1.0)))`
*(It takes the raw probability of arriving on time and penalizes it based on environmental risk multipliers).*

### Phase D: ACT (Decision Engine)
Based on the computed risk, the agent emits a final decision payload:
*   **Critical Breach (`initiate_negotiation`)**: If the adjusted probability drops below 60% (or raw delay > 90 min on a high-weight meeting), the agent acts aggressively to reschedule and terminates the monitoring loop.
*   **High Risk (`soft_heads_up`)**: If probability is <= 85% on an important meeting, it emits a warning but keeps monitoring.
*   **Safe**: Otherwise, it remains silent.

---

## 3. Real-World Execution Examples

Based on our test engine (`testorchestrationagent.py`), here is exactly how the agent behaves in three different scenarios:

### Scenario 1: The "On-Time" Flight
*   **Input:** Flight 2426 is on time.
*   **Agent Logic:** Parses `Status: on_time`. The gatekeeper rule activates.
*   **Output:** `[AmbientTravelOrchestrator] Gatekeeper rule: Flight on time. Committing state; remaining silent.`
*   **Result:** The agent goes back to sleep. No extra APIs are called.

### Scenario 2: The "Delayed" Flight
*   **Input:** Flight 2426 is delayed.
*   **Agent Logic:** 
    1. Parses `Status: delayed`.
    2. Gathers weather, route, and calendar data.
    3. Calculates `raw_delay = 45` minutes.
    4. Computes probability: Base `p=0.78`, Risk Multiplier `mult=1.25` -> `adjusted_p = 0.73`.
    5. Evaluates boundaries: 0.73 is <= 0.85, and meeting weight is high (0.85).
*   **Output:**
    ```json
    {
      "decision": "soft_heads_up",
      "adjusted_probability": 0.73,
      "delay_minutes": 45,
      "meeting_weight": 0.85,
      "delay_multiplier": 1.25,
      "rationale": "Autonomous structural validation cycle executed..."
    }
    ```

### Scenario 3: The "Cancelled" Flight
*   **Input:** Flight 2426 is cancelled.
*   **Agent Logic:** Parses `Status: cancelled`. Gatekeeper rule triggers an immediate severe action.
*   **Output:**
    ```json
    {
      "decision": "cancellation",
      "adjusted_probability": null,
      "delay_minutes": 0,
      "meeting_weight": null,
      "delay_multiplier": 1.0,
      "rationale": "Autonomous structural validation cycle executed..."
    }
    ```


# Connecting and querying the database directly:
# Open the DB
sqlite3 orchestrator_state.db

# Then inside the shell:
.tables
.mode column
.headers on

See your session
SELECT id, state, update_time FROM sessions WHERE app_name = 'AmbientTravelOrchestrator';

See all events for a flight
SELECT id, author, timestamp FROM events WHERE session_id = 'session_UA123_meeting42' ORDER BY timestamp ASC;

SELECT * FROM sessions WHERE id = 'session_123_meeting_abcd';

Exit
.quit


# get the calendar events details from terminal

$ cd /Users/sangeetha/Supportvector2026/capstone/project/GulliverTravels
PYTHONPATH=. uv run python -c "
from backend.src.mcp.tools.config import get_service
from datetime import datetime, timezone
service = get_service()
now = datetime.now(timezone.utc).isoformat()
events = service.events().list(
    calendarId='primary',
    maxResults=10,
    singleEvents=True,
    orderBy='startTime',
    timeMin=now
).execute()
for e in events.get('items', []):
    print(e['id'], '|', e.get('summary','No title'), '|', e['start'].get('dateTime', e['start'].get('date')))
"