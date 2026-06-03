# GulliverTravels: Startup & Run Guide

This guide documents the procedures for starting, running, and testing the GulliverTravels multi-agent system.

---

## 🚀 1. Overview of Services

The application consists of three main components:
1. **FastMCP Server (Port 9000)**: Serves MCP tools (such as live flight status trackers, route details, and Google Calendar integrations).
2. **FastAPI Gateway (Port 8000)**: Serves the agentic endpoints (like `/chat`, `/transcribe`) and exposes the `/api/monitor/status` real-time state database endpoint.
3. **React Frontend (Port 5173)**: Renders the chat portal and the ambient flight monitoring dashboard.

---

## ⚡ 2. Unified Application Startup (Recommended)

A pre-configured startup script is available in the project root to launch all three services concurrently in a single terminal window. The script handles standard output streams and automatically shuts down all services cleanly upon hitting `Ctrl+C`.

```bash
# Launch all services
./start_app.sh
```

---

## 🖥️ 3. Separate Startup Commands

If you prefer to run services in separate terminal tabs for debugging and inspecting individual logs, use the following commands:

### Tab 1: FastMCP Tool Server
Runs the standalone tool server using `uv`:
```bash
uv run python -m backend.src.mcp.fastmcp_server
```

### Tab 2: FastAPI Gateway Server
Runs the FastAPI web server on port 8000 with live auto-reloading:
```bash
PYTHONPATH=. uv run python -m backend.src.travelagent.main
```

### Tab 3: React Frontend Development Server
Spins up the Vite web application on port 5173:
```bash
cd frontend
npm run dev
```

---

## 🧹 4. Testing & State Management Utilities

### A. Resetting Persistent Flight Monitoring States
Since the orchestrator stores historical status and notification dispatch flags (`email_sent: True`) inside the SQLite DB, you must reset/remove the database between test cycles to trigger new alerts:

```bash
# Remove the DB to start fresh
rm orchestrator_state.db
```

### B. Querying SQLite Tables Directly
To view live session states, run:
```bash
sqlite3 orchestrator_state.db
```
Inside the SQLite prompt, query current records:
```sql
.headers on
.mode columns
SELECT id, app_name, user_id, state FROM sessions;
```

---

## 🧪 5. Running Tests

To run the unit/integration test suite:

```bash
# Run tests with pytest
PYTHONPATH=. uv run pytest backend/src/tests/test_call_time_agent.py

# Or run the test script directly
PYTHONPATH=. uv run python backend/src/tests/test_call_time_agent.py
```
