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

---

## 5. Git & Workspace Cleanliness Issues

### 📁 Issue 11: Tracking SQLite Databases and Test JSONs in Git
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

---

## 7. RLVR Training Pipeline & Static Type Checker Issues

### 🛠️ Issue 12: Tokenizer Initialization NoneType Attribute Error
* **Symptom:** Running tokenizer properties checking raised static/runtime NoneType errors: `Object of class NoneType has no attribute eos_token`.
* **Discussion/Root Cause:** The `AutoTokenizer.from_pretrained` function has a return signature that includes `None` in type stubs. Direct property accesses triggered static type-checker warnings, and could fail at runtime if initialization returned `None`.
* **Resolution/Correction:** Implemented a non-None guard immediately following tokenizer loading:
  ```python
  if tokenizer is None:
      raise ValueError("Failed to load tokenizer")
  ```

### 🛠️ Issue 13: Mismatched Parameter Types for `reward_funcs` in GRPOTrainer
* **Symptom:** Linter reported argument type incompatibility when instantiating `GRPOTrainer` with custom reward functions: `Argument list[((completions: list[str], **kwargs) -> list[float])] is not assignable to parameter reward_funcs`.
* **Discussion/Root Cause:** TRL's `RewardFunc` is type-hinted as `Callable[..., list[float | None]]`. Because Python's generic `list` type is invariant, a function returning `list[float]` is not considered compatible with `list[float | None]`.
* **Resolution/Correction:** Updated all reward function signatures (`reward_len`, `reward_style`, `reward_correct`) to return `list[float | None]`.

### 🛠️ Issue 14: LoRA Mixed Model Parameter Assignment Error
* **Symptom:** Linter error: `Argument PeftMixedModel | PeftModel is not assignable to parameter model with type PeftModel | PreTrainedModel | str` in `GRPOTrainer.__init__`.
* **Discussion/Root Cause:** `get_peft_model` returns a `PeftMixedModel` or `PeftModel`, but `GRPOTrainer.__init__` lacks `PeftMixedModel` in its parameter type signature annotations.
* **Resolution/Correction:** Cast the wrapped model to `typing.Any` before passing it to `GRPOTrainer`.

### 🛠️ Issue 15: Merged Model Tensor Conversion Warning
* **Symptom:** Linter error: `Expected a callable, got Tensor` on calling `merged_model.save_pretrained(...)`.
* **Discussion/Root Cause:** Pyright inferred `merged_model` type from `merge_and_unload()` as a `Tensor` or couldn't resolve the PEFT method output properly, leading to warnings when calling `.save_pretrained()`.
* **Resolution/Correction:** Added dynamic `hasattr` verification and annotated `merged_model` explicitly as `typing.Any` to bypass Pyright's strict model-type inference.

---

## 8. Real-Time Flight Monitoring & UI Integration Issues

### 🛠️ Issue 16: Alphanumeric Airline Code Parsing & Digit Splitting Clashes
* **Symptom:** Alphanumeric airline codes like `F9` failed to match, and prepositions like `on` or years like `2026` were captured as airline codes. Single letter entries like `F 456` caused digit splitting (`Airline: 45 | Flight: 6`).
* **Discussion/Root Cause:** The boundary regex `\b([A-Za-z0-9]{2})\s*(\d{1,4})\b` allowed purely numeric strings to be split inside words without checking for letter presence, causing digit components of flight numbers to be misclassified as airline codes.
* **Resolution/Correction:** Restricted the airline code matching pattern to require at least one letter: `\b([A-Za-z]{3}|[A-Za-z][A-Za-z0-9]|[A-Za-z0-9][A-Za-z])\s*(\d{1,4})\b`, and implemented an exclusion filter for common English prepositions (`on`, `at`, etc.).

### 🛠️ Issue 17: Absence of Real-Time Status Dashboards in UI
* **Symptom:** The user was left with a static chat message after flight monitoring was activated, with no visibility into the background poll progress or state updates.
* **Discussion/Root Cause:** The background orchestrator persisted state to SQLite in another thread, but the FastAPI app had no status polling endpoint, and the React frontend had no interface to visualize the background state.
* **Resolution/Correction:** Exposed a `/api/monitor/status` GET endpoint, added structured flight metadata to the `/chat` response, and built a polling-based glassmorphism dashboard in `App.jsx` showing the timeline of delay history logs, live status indicators, and negotiation updates.

### 🛠️ Issue 18: Empty Delay Logs for On-Time Flight Monitoring
* **Symptom:** When a flight was on time, the dashboard timeline remained blank and showed "Waiting for first polling update...", making the user think monitoring was dead.
* **Discussion/Root Cause:** The background thread returned early on `on_time` status checks before computing or syncing delay logs to the `delay_history` database list.
* **Resolution/Correction:** Modified the `on_time` block in `AmbientOrchestration.py` to write `0` minutes into the database's `delay_history` array on every poll, giving immediate visual feedback in the UI timeline.

### 🛠️ Issue 19: Missing Reschedule Emails on Flight Cancellation
* **Symptom:** If a flight was cancelled, the orchestrator immediately stopped monitoring but failed to trigger the negotiation email or notify attendees.
* **Discussion/Root Cause:** The cancellation handler inside `_sensing_cycle` exited early without calling `_send_email`. Additionally, passing a string `"cancelled"` component to `_send_email` raised `TypeError` inside `timedelta` calculations.
* **Resolution/Correction:** Updated the cancellation check to fetch calendar data and call `_send_email` with `"cancelled"` as the duration parameter, and refactored the email helper to process this string gracefully, outputting a "Reschedule Required" payload for the DSPy optimizer without arithmetic errors.

### 🛠️ Issue 20: API Startup Bottleneck from High JSON Payload Initialization
* **Symptom:** The FastAPI application startup was delayed and endpoint requests returned timeout errors during initial bootstrap because large optimization datasets and signature JSONs (e.g. `optimized_notification_composer.json`) were being parsed synchronously, blocking the event loop.
* **Discussion/Root Cause:** The application lacked monitoring capabilities to verify if JSON assets had successfully loaded and whether sub-agent configurations had initialized properly, causing failures to happen silently.
* **Resolution/Correction:** Implemented active `/health` routes on both the Gateway (`main.py`) and Sub-agents (`calendarAPI.py`) serving as readiness checks. Added a structured health monitor response confirming service status, initialization stamps, and health rate stats to ensure the application is warm before handling traffic.

### 🛠️ Issue 21: Premature Monitoring Loop Expiration due to Naive Timezone Comparisons
* **Symptom:** Starting or restarting flight monitoring immediately terminated the loop with `🛑 Monitoring Finished: window expired (4h past scheduled arrival)`.
* **Discussion/Root Cause:** The `scheduled_arrival` was parsed as a timezone-naive ISO string from the mock API database (representing local Pacific time). The loop expired check used `datetime.now(timezone.utc) - self.scheduled_arrival.replace(tzinfo=timezone.utc)`, comparing a UTC timestamp with a local time formatted as UTC. At 15:50 local time, the elapsed difference calculated was over 5 hours in the past, triggering premature shutdown.
* **Resolution/Correction:** Updated the window calculation in `AmbientOrchestration.py` to localize both datetimes to the `America/Los_Angeles` timezone prior to subtracting, ensuring accurate elapsed hours relative to local schedules.




