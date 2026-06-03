# GulliverTravels Architecture

This document provides a high-level overview of the GulliverTravels system architecture and the flow of data across the various components.

## 🏗️ System Overview

GulliverTravels is a multimodal agentic system consisting of a React frontend and a FastAPI backend powered by the **Google Agent Development Kit (ADK)** and the **Model Context Protocol (MCP)**.

```mermaid
graph TD
    subgraph Frontend Client
        A[React UI / Vite]
    end

    subgraph FastAPI Backend Gateway (main.py)
        B[FastAPI Routes]
        C[InMemoryRunner]
        D[root_agent agent.py]
        STATUS_API[GET /api/monitor/status]
    end

    subgraph Persistent Database
        DB[(SQLite State DB<br/>orchestrator_state.db)]
    end

    subgraph Background Ambient Loop (AmbientOrchestration.py)
        ORCH[AmbientOrchestratorAgent]
        COMM[Committee Agents<br/>Time, Risk, Impact]
        DSPy[DSPy Notification Composer]
    end

    subgraph External Protocols & Services
        MCP[FastMCP Server<br/>tools.py]
        CalAgent[CalendarAgent ADK]
        GCal[Google Calendar API]
    end

    %% Client Interactions
    A -->|1. POST /chat| B
    A -->|5. Poll status every 3s| STATUS_API

    %% Chat Path
    B -->|2. Manage chat sessions| C
    C -->|3. Run| D
    D -->|4. Trigger background task| ORCH

    %% Status Path
    STATUS_API -->|6. Query session state| DB
    
    %% Background Loop
    ORCH -->|7. Heartbeat Poll| MCP
    ORCH -->|8. Sync status & logs| DB
    ORCH -->|9. Run Decisions| COMM
    ORCH -->|10. Compose Emails| DSPy
    ORCH -->|11. Schedule Update| CalAgent
    CalAgent -->|12. Reschedule & Email Guests| GCal
```

---

## 📂 Core Components

### 1. Frontend (`frontend/src/App.jsx`)
- **Role**: The user interface.
- **Flow**: 
    1. Generates a unique `session_id` on load to track state.
    2. Sends user messages to `http://localhost:8000/chat`.
    3. Handles audio recording and sends it to `/transcribe`.
- **Key Files**: `App.jsx`, `main.jsx`, `package.json`.

### 2. Backend Gateway (`backend/src/travelagent/main.py`)
- **Role**: The orchestrator and entry point for all API requests.
- **Flow**:
    1. Receives the `ChatRequest` (message + user_id + session_id).
    2. Uses a global `InMemoryRunner` to maintain conversation history.
    3. Triggers the `root_agent` to process the message.
    4. Aggregates streaming events into a final response.
- **Endpoints**: `/chat`, `/transcribe`, `/tools/add`.

### 3. Agent Definition (`backend/src/travelagent/agent.py`)
- **Role**: Defines the "brain" of the system.
- **Flow**:
    1. Configured with a model via `LiteLlm` (pointing to a custom OpenAI-compatible endpoint).
    2. Contains the system instructions that define the agent's personality and behavior.
    3. Orchestrates tool calls if needed.

### 4. MCP Server (`backend/src/travelagent/server.py`)
- **Role**: A standalone tool server using the **Model Context Protocol**.
- **Flow**:
    1. Exposes specific functions (like `add_numbers`) as tools.
    2. The agent can "discover" and call these tools dynamically.
    3. Runs on a separate port (8001 by default).

---

## 🔄 Request Lifecycle (Example)

1. **User Types**: "Add 10 and 20" in the browser.
2. **Frontend**: Sends a POST request to `/chat` with `session_id="xyz"`.
3. **main.py**: 
   - Looks up `session_id="xyz"` in the `InMemoryRunner`.
   - Passes the request to `root_agent`.
4. **agent.py (ADK)**:
   - Sees the request requires a tool call.
   - Calls the `add_numbers` tool.
5. **server.py**: Executes `10 + 20` and returns `30`.
6. **main.py**: Receives the result, finishes the agent execution, and returns "The result is 30" to the frontend.
7. **Frontend**: Displays "The result is 30" to the user.

---

## 🛠️ Technology Stack

- **Frontend**: React, Vite, Vanilla CSS.
- **Backend API**: FastAPI, Uvicorn.
- **Agent Framework**: Google ADK (Agent Development Kit).
- **LLM Integration**: LiteLLM (via ADK extensions).
- **Tool Protocol**: FastMCP (Model Context Protocol).
- **Environment**: Python 3.13+, `uv` for package management.

##
run the orchestration agent

(gullivertravels) (base) sangeetha@Sangeethas-MacBook-Pro GulliverTravels % uv run python -m backend.src.travelagent.testorchestrationagent

##
View the data in the orchestration agent

(base) sangeetha@Sangeethas-MacBook-Pro GulliverTravels % source .venv/bin/activate
(gullivertravels) (base) sangeetha@Sangeethas-MacBook-Pro GulliverTravels % sqlite3 orchestrator_state.db
SQLite version 3.43.2 2023-10-10 13:08:14
Enter ".help" for usage hints.
sqlite> .tables
adk_internal_metadata  events                 user_states          
app_states             sessions             
sqlite> SELECT * FROM app_states;
AmbientTravelOrchestrator|{}|2026-05-18 20:13:59
sqlite> 


CREATE TABLE adk_internal_metadata (
	"key" VARCHAR(128) NOT NULL, 
	value VARCHAR(256) NOT NULL, 
	PRIMARY KEY ("key")
);
CREATE TABLE sessions (
	app_name VARCHAR(128) NOT NULL, 
	user_id VARCHAR(128) NOT NULL, 
	id VARCHAR(128) NOT NULL, 
	state TEXT NOT NULL, 
	create_time DATETIME NOT NULL, 
	update_time DATETIME NOT NULL, 
	PRIMARY KEY (app_name, user_id, id)
);
CREATE TABLE app_states (
	app_name VARCHAR(128) NOT NULL, 
	state TEXT NOT NULL, 
	update_time DATETIME NOT NULL, 
	PRIMARY KEY (app_name)
);
CREATE TABLE user_states (
	app_name VARCHAR(128) NOT NULL, 
	user_id VARCHAR(128) NOT NULL, 
	state TEXT NOT NULL, 
	update_time DATETIME NOT NULL, 
	PRIMARY KEY (app_name, user_id)
);
CREATE TABLE events (
	id VARCHAR(128) NOT NULL, 
	app_name VARCHAR(128) NOT NULL, 
	user_id VARCHAR(128) NOT NULL, 
	session_id VARCHAR(128) NOT NULL, 
	invocation_id VARCHAR(256) NOT NULL, 
	timestamp DATETIME NOT NULL, 
	event_data TEXT, 
	PRIMARY KEY (id, app_name, user_id, session_id), 
	FOREIGN KEY(app_name, user_id, session_id) REFERENCES sessions (app_name, user_id, id) ON DELETE CASCADE
);
CREATE INDEX idx_events_app_user_session_ts ON events (app_name, user_id, session_id, timestamp DESC);

#run the AmbientOrchestration agent
uv run python -m backend.src.travelagent.AmbientOrchestration