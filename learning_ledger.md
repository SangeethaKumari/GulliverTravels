# Gulliver Travels Project: Learning & Troubleshooting Ledger

This ledger compiles the technical, structural, and conceptual issues identified, discussed, and resolved during the stabilization of the GulliverTravels multi-agent orchestrator.

---

## 1. Technical & Code Issues

### 🛠️ Issue 1: Gemini Model Initializer API Format Clashes
* **Symptom:** LiteLLM / Gemini returned `400` or `BadRequestError` errors depending on how the model name was structured.
* **Discussion/Root Cause:** Google ADK relies on LiteLLM under the hood. 
  * DSPy expects `gemini/gemini-2.5-flash`.
  * Other ADK agents expected pure `gemini-2.5-flash`.
  * Passing `google/gemini-2.5-flash` caused LiteLLM to fail because the provider prefix was incorrect.
* **Resolution/Correction:** Standardized model configuration across modules:
  * For DSPy: `gemini/gemini-2.5-flash`.
  * For ADK agents: `gemini-2.5-flash`.

### 🛠️ Issue 2: OOP Signature Error (Implicit `self` Parameter)
* **Symptom:** Running the orchestrator failed with: `Expected 0 positional arguments, got 1 (including implicit self) in function AmbientOrchestratorAgent._heartbeat`.
* **Discussion/Root Cause:** The `_heartbeat()` async task was defined as a standard function inside the class but was called via the class context without taking the instance (`self`) argument in its signature.
* **Resolution/Correction:** Changed the method definition signature to `async def _heartbeat(self):`.

### 🛠️ Issue 3: DSPy Network Connection Timeout (15s Limit)
* **Symptom:** The execution loop would hang and timeout during the notification composition phase with: `DSPy cloud module timed out after 15 seconds!`.
* **Discussion/Root Cause:** The compiled DSPy optimizer configuration (`dspyoptimizer.py`) hardcoded a local private IP address (`10.0.10.51:8124`) for the reasoning LLM. When running in a different environment where this IP is unreachable, the network socket hung until the 15-second timeout dropped it.
* **Resolution/Correction:** Implemented a dynamic fallback strategy. If `10.0.10.51` is unreachable or `GOOGLE_API_KEY` is available, the optimizer dynamically redirects inference calls to `gemini/gemini-2.5-flash`, executing prompts successfully in milliseconds.

### 🛠️ Issue 4: Python Module & Path Import Failures
* **Symptom:** Python could not locate `backend.src.mcp...` modules, throwing `ModuleNotFoundError` during execution.
* **Discussion/Root Cause:** Conflicting package structures between standard `python` executing scripts locally vs imports run via `uv run` relative to the workspace root directory.
* **Resolution/Correction:** Standardized execution commands to run as modules (`python -m backend.src.travelagent.AmbientOrchestration`) from the root directory to maintain clean absolute import paths.

---

## 2. Pydantic & Structural Validation Issues

### 📐 Issue 5: Strict Type Matching Violations (Float vs. Int)
* **Symptom:** Passing delay parameters to Pydantic models threw validation/type errors.
* **Discussion/Root Cause:** Raw calculations from timedelta operations or time estimation returns resulted in `float` delay values. The downstream Pydantic schemas and `_send_email` signatures strictly expected `int`.
* **Resolution/Correction:** Explicitly cast variables to target types before model execution:
  `await self._send_email(flight_info, int(raw_delay), adjusted_p, calendar_info)`

### 📐 Issue 6: Calendar Agent Invocation & Runner Integration
* **Symptom:** Instantiating and executing commands through `CalendarAgent` directly inside the async polling loop threw context errors.
* **Discussion/Root Cause:** The integration originally attempted to run the agent in the background using `InMemoryRunner(agent=CalendarAgent)` with `auto_create_session = True`. However, this async runner execution loop conflicted with the orchestrator's synchronous database sync commands.
* **Resolution/Correction:** Refactored the orchestrator to instantiate `CalendarAgent()` directly and dispatch updates using `asyncio.get_running_loop().run_in_executor(None, agent.execute, prompt)` to isolate blocking ADK operations onto a separate execution thread.

---

## 3. State & Orchestration Loop Issues

### 🔄 Issue 7: SQLite Persistent State Block ("email already sent")
* **Symptom:** During testing, the orchestrator would print `Email notification already sent. Skipping dispatch.` and refuse to send new notifications, even after flight delay changes.
* **Discussion/Root Cause:** The session state `email_sent: True` was persisted in SQLite. Since state is saved across runs, consecutive test runs remained blocked by the historical record of the same session ID.
* **Resolution/Correction:** Created database purging scripts. For testing/demo cycles, the SQLite records must be deleted:
  `sqlite3 orchestrator_state.db "DELETE FROM events; DELETE FROM sessions;"`

### 🔄 Issue 8: Mock State Pollution (Flight Status Counter)
* **Symptom:** The flight delay status suddenly reported a 90-minute delay on the very first poll of a clean execution run.
* **Discussion/Root Cause:** The mock tool `flight_status_realtime` in `tools.py` tracks calls using a global memory counter (`FLIGHT_STATUS_CALL_COUNT`). Because the background FastMCP server was not restarted and consecutive runs occurred within the 120-second timeout window, the counter kept incrementing across runs, immediately falling into the max delay `else` block on new runs.
* **Resolution/Correction:** Standardized instructions to allow a 2-minute cooldown between tests to reset the global counter, or restart the FastMCP server terminal process.

---

## 4. Google API & Integration Issues

### 📅 Issue 9: Hardcoded vs. Dynamic Rescheduling Delays
* **Symptom:** The flight delay logged was 90 minutes, but the rescheduled calendar meeting was only shifted by 1 hour.
* **Discussion/Root Cause:** The `CalendarAgent` reschedule payload had a hardcoded `timedelta(hours=1)` offset, which created a mismatch and risked traveler tardiness for meetings with longer delays.
* **Resolution/Correction:** Replaced the hardcoded time calculation with dynamic values using `timedelta(minutes=delay_minutes)`, aligning the calendar reschedule directly to the flight arrival delay.

### 📅 Issue 10: Silent Calendar Updates (Missing Guest Notifications)
* **Symptom:** When the meeting was rescheduled, only the organizer's calendar was updated; other guests/attendees did not receive emails.
* **Discussion/Root Cause:** In Google Calendar API, updates are silent by default. To notify all attendees, the `sendUpdates="all"` parameter must be explicitly passed in the `update()` payload. It was missing in `edit_calendar.py`.
* **Resolution/Correction:** Added the `sendUpdates="all"` argument to `service.events().update()` inside `backend/src/mcp/tools/edit_calendar.py`.

### 📅 Issue 11: Email Alternative Times and Calendar Rescheduled Time Mismatch
* **Symptom:** The email notification sent to attendees proposed alternative meeting times (e.g. 4:30 PM or 5:30 PM), but the actual rescheduled calendar event was set to a different time (e.g. 5:00 PM), causing confusion.
* **Discussion/Root Cause:** The `proposed_times` sent as inputs to the DSPy notification composer were hardcoded to `start_dt + 1 hour` and `start_dt + 2 hours`, whereas the calendar event was updated dynamically using `start_dt + delay_minutes`.
* **Resolution/Correction:** Updated both calculations to be driven by `delay_minutes` so they are fully aligned. The proposed times are now dynamically calculated as `start_dt + delay_minutes` and `start_dt + delay_minutes + 30`, matching the actual rescheduled calendar event start time.

### 📅 Issue 12: Timezone Date Shifts on UTC Event Formats
* **Symptom:** The calendar event date shifted incorrectly to the next day (May 31 instead of May 30) for attendees, resulting in timezone confusion.
* **Discussion/Root Cause:** Google Calendar API returns meeting times in UTC serialization formats (e.g., `'2026-05-31T00:00:00Z'`). If the code formats this datetime string directly without first converting it to the local Pacific timezone, the naive string parsed by the agent represents the UTC day. When saved back to the calendar, it shifts the event forward by the timezone offset (7 hours), moving it to May 31.
* **Resolution/Correction:** Added explicit `.astimezone(tz)` conversions (using `zoneinfo.ZoneInfo("America/Los_Angeles")`) to all fetched datetime strings in `AmbientOrchestration.py`, `edit_calendar.py`, and `check_conflicts.py` before any formatting or editing occurs.

---

## 5. Git & Workspace Cleanliness Issues

### 📁 Issue 13: Tracking SQLite Databases and Test JSONs in Git
* **Symptom:** Local database files (`orchestrator_state.db`) and transient test runs were getting indexed by git, leading to merge conflicts and clutter in the commit history.
* **Discussion/Root Cause:** The workspace root did not have specific rules ignoring SQLite extensions (`.db`, `.db-journal`) or generated developer cache directories.
* **Resolution/Correction:** Configured `.gitignore` to explicitly ignore persistent SQLite state files (`orchestrator_state.db`) and local environment overrides, keeping the repository history clean.

---

## 6. Key Conceptual Learnings

### 💡 Learning 1: DSPy Program Serialization vs. Active LMs
* **Concept:** Compiling a DSPy optimizer and saving a JSON state (like `optimized_notification_composer.json`) does not mean the program is now self-sufficient or static.
* **Takeaway:** The JSON contains instructions and optimal examples (demos), but executing a new scenario at runtime still requires a live connection to an active LLM to generate the final text based on those compiled inputs.

### 💡 Learning 2: Safeguard Constraints in Agent Committees
* **Concept:** A committee-based decision (e.g., merging `TimeAgent`, `RiskAgent`, and `ImpactAgent` outputs) should have logical overrides.
* **Takeaway:** Even if `adjusted_probability` is calculated above the reschedule threshold (e.g., 73%), a strict safeguard like `(delay >= 90 mins and meeting_weight > 0.7)` is necessary to bypass model estimations and guarantee negotiation on high-importance, long-delay scenarios.
