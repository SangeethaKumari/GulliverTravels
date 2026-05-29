# SQLite Database Documentation: `orchestrator_state.db`

The Ambient Travel Orchestrator uses a local SQLite database (`orchestrator_state.db`) managed by the `google-adk` `DatabaseSessionService` (SQLAlchemy async dialect) to persist user context, flight delay histories, and event logs across restarts.

---

## 1. Database Schema

The database consists of the following 5 tables:

### 📋 Table: `sessions`
Stores active session states, serializing context fields (like flight delays, emails sent, and scheduled thresholds).
* **`app_name`** (`VARCHAR(128)`): The name of the agent application. [PK]
* **`user_id`** (`VARCHAR(128)`): Unique traveler identifier. [PK]
* **`id`** (`VARCHAR(128)`): Active session identifier. [PK]
* **`state`** (`TEXT`): Serialized JSON payload containing state variables (e.g., `delay_history`, `email_sent`).
* **`create_time`** (`DATETIME`): Creation timestamp.
* **`update_time`** (`DATETIME`): Modification timestamp.

### 📋 Table: `events`
Records all sequential step events processed during the agent lifecycle (sensing, thinking, acting).
* **`id`** (`VARCHAR(128)`): Event identifier. [PK]
* **`app_name`** (`VARCHAR(128)`): The name of the agent application. [PK]
* **`user_id`** (`VARCHAR(128)`): Unique traveler identifier. [PK]
* **`session_id`** (`VARCHAR(128)`): Reference to the parent session. [PK]
* **`invocation_id`** (`VARCHAR(256)`): Invocation correlation trace ID.
* **`timestamp`** (`DATETIME`): Event insertion timestamp.
* **`event_data`** (`TEXT`): Serialized event parameters.

### 📋 Table: `app_states`
Global application settings.
* **`app_name`** (`VARCHAR(128)`): App identifier. [PK]
* **`state`** (`TEXT`): Global configurations.
* **`update_time`** (`DATETIME`): Modification timestamp.

### 📋 Table: `user_states`
Traveler preferences and persistent user records.
* **`app_name`** (`VARCHAR(128)`): App identifier. [PK]
* **`user_id`** (`VARCHAR(128)`): Traveler identifier. [PK]
* **`state`** (`TEXT`): Traveler configurations.
* **`update_time`** (`DATETIME`): Modification timestamp.

### 📋 Table: `adk_internal_metadata`
Internal schema and migration version tracking parameters.
* **`key`** (`VARCHAR(128)`): Metadata key. [PK]
* **`value`** (`VARCHAR(256)`): Schema version identifier.

---

## 2. Sample SQL Queries

Use these queries within your favorite SQLite client (e.g. `sqlite3`, DBeaver, or VS Code SQLite extension) to inspect and debug orchestration cycles.

### 🔍 Query 1: Extract Active Session Variables
Displays the current state and delay lists.
```sql
SELECT 
    id AS session_id,
    user_id,
    state,
    update_time 
FROM sessions;
```

### 🔍 Query 2: Extract Specific JSON Keys (SQLite JSON1 Extension)
Extracts the historical list of delay minutes from the serialized text field.
```sql
SELECT 
    id AS session_id,
    json_extract(state, '$.delay_history') AS delay_history,
    json_extract(state, '$.email_sent') AS email_sent
FROM sessions;
```

### 🔍 Query 3: Retrieve Chronological Executions (Sensing/Acting events)
Displays the logs of what actions the agent took.
```sql
SELECT 
    timestamp,
    session_id,
    id AS event_id,
    invocation_id
FROM events 
ORDER BY timestamp ASC;
```

### 🧹 Query 4: Clear Session State (Environment Reset)
Completely resets the orchestrator state to test clean start scenarios.
```sql
-- Disable foreign keys temporarily if needed
PRAGMA foreign_keys = OFF;

DELETE FROM events;
DELETE FROM sessions;
DELETE FROM user_states;
DELETE FROM app_states;

PRAGMA foreign_keys = ON;
```

---

## 3. Command Line Inspection Utility

A Python inspection utility `inspect_db.py` is included in the project root directory. Run it to inspect all SQLite tables and print formatted JSON states to the terminal:

```bash
python inspect_db.py
```
