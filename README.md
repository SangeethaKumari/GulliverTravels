# GulliverTravels

GulliverTravels is an AI-powered assistant designed to help travelers plan their trips, choose the right gear, and maintain their bikes. The project uses the Google Agent Development Kit (ADK) for agentic logic and Model Context Protocol (MCP) for tool integration.

Detailed information about the system flow and components can be found in the [Architecture Document](./ARCHITECTURE.md).

## Project Structure

- `backend/src/travelagent/`: Core backend logic.
  - `agent.py`: Google ADK Agent definition (configured with LiteLLM).
  - `main.py`: FastAPI server that integrates the agent and proxies tool calls.
  - `server.py`: FastMCP server exposing tools (e.g., math utilities).
- `frontend/`: (Work in progress) Vite-based frontend.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) (for Python package management)
- Python 3.13+
- A Google Gemini API Key or LiteLLM Endpoint

## Setup

1. **Clone the repository** (if not already done).
2. **Environment Variables**:
   Create a `.env` file in the root directory and add the following:
   ```env
   GOOGLE_API_KEY=your_gemini_api_key_here
   API_SECRET_TOKEN=your-secret-token
   MCP_SERVER_URL=http://localhost:8001
   
   # LiteLLM Configuration (Optional)
   LITELLM_API_BASE=http://10.0.10.51:8124/v1
   LITELLM_API_KEY=sv-openai-api-key
   ```
3. **Install Dependencies**:
   ```bash
   uv sync
   # Ensure ADK extensions are installed for LiteLLM support
   uv pip install "google-adk[extensions]"
   ```

## Running the Application

The application consists of two server components that need to be running simultaneously.

### 1. Start the MCP Server
The MCP server provides tools that the AI agent can use.
```bash
# From the root directory:
PYTHONPATH=backend/src uv run python -m travelagent.server

# OR from the backend/src directory:
uv run python -m travelagent.server
```
*Port: 8001*

### 2. Start the FastAPI Server (Backend)
The FastAPI server is the main entry point for the application. It manages agentic logic and session persistence.
```bash
# From the root directory:
PYTHONPATH=backend/src uv run python -m travelagent.main

# OR from the backend/src directory:
uv run python -m travelagent.main
```
*Port: 8000*

### 3. Start the Frontend
The frontend is a Vite-based React application.
```bash
# From the root directory:
cd frontend
npm install # done first time or when dependencies change
npm run dev # run the frontend
```
*Port: 5173 (default)*

### DB clearing
rm orchestrator_state.db 

## API Usage

### Chat with the TravelAgent
Send a message to the agent. Note that `session_id` is required for multi-turn conversations.

```bash
curl -X POST http://localhost:8000/chat \
     -H "Authorization: Bearer your-secret-token" \
     -H "Content-Type: application/json" \
     -d '{"message": "How do I perform a low-speed U-turn?", "session_id": "unique-session-id"}'
```

### Call a Tool (Proxy)
Directly call a tool exposed via the MCP server.

```bash
curl -X POST http://localhost:8000/tools/add \
     -H "Authorization: Bearer your-secret-token" \
     -H "Content-Type: application/json" \
     -d '{"a": 10, "b": 20}'
```

## Development

- The backend uses `uvicorn` with hot-reload enabled in `dev` mode.
- To change the agent's behavior or model configuration (LiteLLM vs Gemini), edit `backend/src/travelagent/agent.py`.
- To add new tools, edit `backend/src/travelagent/server.py`.
- Session history is managed in-memory via `InMemoryRunner` in `main.py`.


## 🧪 Agent Evaluation Matrix & CI/CD Pipeline

This project uses an automated, data-driven testing framework to validate the state-machine logic, string parsing, and decision-making capabilities of the `AmbientOrchestratorAgent`. 

Instead of relying on unstable live API connections, we evaluate the agent's behavior against a localized **Golden Dataset** that simulates real-world flight timelines.

---

### 📅 When Does the Evaluation File Run?

The evaluation suite runs under two distinct conditions:

#### 1. Automatically in the Cloud (CI/CD Guardrails)
Every time a developer interacts with the central repository, the GitHub Actions automation runner wakes up. The file `.github/workflows/agent-eval.yml` triggers the evaluation matrix automatically on:
* **Any `push` event** to the `main` or `develop` branches.
* **Any `pull_request` event** targeting the `main` branch.

If any code modification accidentally breaks a database transaction, messes up datetime delta calculations, or blocks a decision ledger event, **the pipeline halts immediately**, prevents the code from merging, uploads the corrupted `.db` log file for debugging, and dispatches a high-priority alert to the team's Slack channel.

#### 2. Manually on Your Local Machine
Developers should run the evaluation suite locally *before* pushing code to remote branches to catch breaking regressions early.

---

### 💻 How to Run the Evaluation Locally

Make sure you are in the project root directory and your python virtual environment is activated, then use the following commands:

#### Run the Standard Evaluation Matrix
To execute the baseline verification assertions across all mock scenarios:
```bash

uv run pytest backend/src/tests/test_eval_matrix.py 