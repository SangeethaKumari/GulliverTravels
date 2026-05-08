
import os
import uvicorn
import asyncio
import logging

import time
import httpx


from typing import Optional
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Import Google ADK components
from google.adk.runners import InMemoryRunner
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

# Import our root agent
from .agent import root_agent

load_dotenv()

# Global runner instance to persist sessions across requests
runner = InMemoryRunner(agent=root_agent)
runner.auto_create_session = True

# ── Logging ───────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────
MCP_SERVER_URL  = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN", "your-secret-token")

security = HTTPBearer()

# ── Auth ──────────────────────────────────────────────
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return credentials.credentials

# ── Lifespan ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 GulliverTravels API starting up...")
    yield
    logger.info("🛑 GulliverTravels API shutting down...")

# ── App Init ──────────────────────────────────────────
app = FastAPI(
    title="GulliverTravels API",
    version="0.1.0",
    description="FastAPI service powering GulliverTravels — backed by Google ADK + MCP",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request Logging ───────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(f"{request.method} {request.url.path} → {response.status_code} ({duration}ms)")
    return response

# ── Global Error Handler ──────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

# ── Pydantic Models ───────────────────────────────────
class ChatRequest(BaseModel):
    prompt: Optional[str] = None
    message: Optional[str] = None # Support both
    user_id: str = "default_user"
    session_id: str = "default_session"

class TranscribeRequest(BaseModel):
    audio_data: str # Base64 audio data
    user_id: str = "default_user"
    session_id: str = "default_session"

class AddRequest(BaseModel):
    a: float
    b: float

class AddResponse(BaseModel):
    result: float
    operation: str


# ── Companion Models ──────────────────────────────────
class CompanionRequest(BaseModel):
    flight_number: str = "UA123"
    user_id: str = "user-1"
    scenario: Optional[str] = None  # A, B, C, D — or None for current mock state


class CompanionScenarioRequest(BaseModel):
    scenario: str  # A, B, C, D

# ── Routes ────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "GulliverTravels API"}

@app.post("/chat")
async def chat(request_body: ChatRequest, token: str = Depends(verify_token)):
    message = request_body.prompt or request_body.message
    if not message:
        raise HTTPException(status_code=400, detail="No message or prompt provided")
    
    try:
        # We use the global runner which has session persistence
        new_message = types.Content(role="user", parts=[types.Part(text=message)])
        events = runner.run(user_id=request_body.user_id, session_id=request_body.session_id, new_message=new_message)
         
        full_response_text = ""
        for event in events:
            if hasattr(event, 'content') and event.content:
                # We extract the text from the current event
                current_text = "".join([part.text for part in event.content.parts if part.text])
                if current_text.strip():
                    # Instead of +=, we use = to ensure we only get the LATEST agent's final answer
                    full_response_text = current_text
        
        return {"response": full_response_text.strip() or "No response from agent"}
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe")
async def transcribe(request: TranscribeRequest, token: str = Depends(verify_token)):
    """
    Transcribes audio data using Gemini.
    """
    try:
        import base64
        # Remove the data URL prefix if present
        if "," in request.audio_data:
            base64_data = request.audio_data.split(",")[1]
        else:
            base64_data = request.audio_data
        
        audio_bytes = base64.b64decode(base64_data)
        
        audio_part = types.Part.from_bytes(
            data=audio_bytes,
            mime_type="audio/webm" # Frontend sends webm
        )
        
        # Initialize the LiteLLM model with the custom endpoint
        llm = LiteLlm(
            model="gemini/gemini-3-pro-preview",
            api_base=os.getenv("LITELLM_API_BASE", "http://10.0.10.51:8124/v1"),
            api_key=os.getenv("LITELLM_API_KEY", "sv-openai-api-key")
        )
        
        # Initialize an LlmAgent for transcription
        agent = LlmAgent(name="transcriber", model=llm)
        
        # Prepare the content. 
        # Note: We include the audio_part, but LiteLlm/ADK extensions must support multimodal input for this to work.
        new_message = types.Content(role="user", parts=[
            audio_part,
            types.Part(text="Please transcribe this audio exactly as spoken. Return ONLY the transcription.")
        ])
        
        # Execute the agent
        response = agent.execute(new_message=new_message)
        
        transcription = response.text.strip()
        return {"transcription": transcription}
        
    except Exception as e:
        logger.error(f"Transcription Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/add", response_model=AddResponse)
async def call_add_tool(
    payload: AddRequest,
    token: str = Depends(verify_token)
):
    try:
        async with httpx.AsyncClient() as client:
            # We assume the MCP server is using HTTP or SSE and exposed at /mcp or similar.
            # However, for a simple proxy test, we'll try to follow the likely FastMCP structure.
            mcp_rpc_payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "add_numbers",
                    "arguments": {"a": payload.a, "b": payload.b}
                },
                "id": 1
            }
            # Note: The exact path depends on how FastMCP is running. 
            # If it's pure SSE, it might be different. 
            # For now, we'll point to /mcp which is the default for HTTP transport.
            response = await client.post(
                f"{MCP_SERVER_URL}/mcp",
                json=mcp_rpc_payload,
                timeout=10.0
            )
            
            if response.status_code == 404:
                # Try fallback or just report 404
                raise HTTPException(status_code=503, detail="MCP tool endpoint /mcp not found. Check transport/path.")
                
            response.raise_for_status()
            rpc_result = response.json()
            
            # Extract the result from JSON-RPC response
            if "error" in rpc_result:
                raise HTTPException(status_code=400, detail=str(rpc_result["error"]))
            
            # FastMCP tools usually return a list of content items.
            # We expect a dict with "result" and "operation".
            content = rpc_result.get("result", {}).get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                # Try to parse the text as JSON or just return it
                import json
                try:
                    return json.loads(content[0].get("text", "{}"))
                except:
                    return {"result": 0.0, "operation": content[0].get("text", "unknown")}
            
            return rpc_result.get("result", {})

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="MCP server unreachable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="MCP server timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Companion Endpoints ───────────────────────────────
from .companion import mocks as companion_mocks
from .companion.orchestrator import Orchestrator as CompanionOrchestrator
from .companion.composer import HeuristicComposer
from .companion.scenarios import scenario_A, scenario_B, scenario_C, scenario_D
from datetime import datetime, timezone

_SCENARIO_MAP = {
    "A": scenario_A,
    "B": scenario_B,
    "C": scenario_C,
    "D": scenario_D,
}


@app.post("/companion/scenario")
async def set_companion_scenario(
    body: CompanionScenarioRequest,
    token: str = Depends(verify_token)
):
    """Load a predefined test scenario (A/B/C/D) into the mock layer."""
    key = body.scenario.upper()
    factory = _SCENARIO_MAP.get(key)
    if not factory:
        raise HTTPException(status_code=400,
                            detail=f"Unknown scenario '{body.scenario}'. Use A, B, C, or D.")
    state = factory()
    companion_mocks.set_scenario(state)
    companion_mocks.set_now(datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc))
    logger.info(f"Companion scenario set to {key}: {state.name}")
    return {"scenario": key, "name": state.name}


@app.post("/companion/run")
async def run_companion(
    body: CompanionRequest,
    token: str = Depends(verify_token)
):
    """
    Run one companion orchestration cycle.
    Optionally set a scenario first via the `scenario` field.
    Returns the full decision, notifications, calendar updates, and rides.
    """
    if body.scenario:
        key = body.scenario.upper()
        factory = _SCENARIO_MAP.get(key)
        if not factory:
            raise HTTPException(status_code=400,
                                detail=f"Unknown scenario '{body.scenario}'.")
        companion_mocks.set_scenario(factory())
        companion_mocks.set_now(datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc))

    try:
        orch = CompanionOrchestrator(user_name="Sam",
                                     composer=HeuristicComposer())
        result = orch.run_cycle(flight_number=body.flight_number,
                                user_id=body.user_id)

        return {
            "scenario": result.scenario,
            "decision": result.decision.decision,
            "p_on_time": result.decision.p_on_time,
            "adjusted_p_on_time": result.decision.adjusted_p_on_time,
            "meeting_weight": result.decision.meeting_weight,
            "risk_multiplier": result.decision.risk_multiplier,
            "risk_factors": result.decision.risk_output.risk_factors,
            "rationale": result.decision.rationale,
            "time_rationale": result.decision.time_output.rationale,
            "risk_rationale": result.decision.risk_output.rationale,
            "impact_rationale": result.decision.impact_output.rationale,
            "notifications": [
                {
                    "channel": n["channel"],
                    "to": n["to"],
                    "message": n["message"],
                    "rewards": n["rewards"],
                }
                for n in result.log.notifications
            ],
            "calendar_updates": result.log.calendar_updates,
            "rides_booked": result.log.rides_booked,
            "rides_cancelled": result.log.rides_cancelled,
        }
    except Exception as e:
        logger.error(f"Companion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/companion/tools")
async def list_companion_tools(token: str = Depends(verify_token)):
    """List the MCP tools available for the travel companion."""
    return {
        "tools": [
            {"name": "get_flight_status", "description": "Real-time flight status"},
            {"name": "get_weather", "description": "Weather conditions and trend"},
            {"name": "estimate_route", "description": "Drive time under current traffic"},
            {"name": "get_calendar_events", "description": "Upcoming calendar events"},
            {"name": "book_ride", "description": "Pre-book a rideshare"},
            {"name": "cancel_ride", "description": "Cancel a booked ride"},
        ]
    }


# ── Entry Point ───────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    ENV = os.getenv("APP_ENV", "dev")

    if ENV == "dev":
        logger.info("🔧 Running in DEV mode — hot reload enabled")
        # Note: using "travelagent.main:app" because of the package structure
        uvicorn.run("travelagent.main:app", host="0.0.0.0", port=8000, reload=True, workers=1, log_level="debug")
    else:
        logger.info("🚀 Running in PROD mode")
        uvicorn.run("travelagent.main:app", host="0.0.0.0", port=8000, reload=False, workers=4, log_level="warning")
