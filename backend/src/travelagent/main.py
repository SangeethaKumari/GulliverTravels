
import os
import uvicorn
import asyncio
import logging

import time
import httpx


from datetime import date
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

def get_next_meeting_id(landing_time_iso: Optional[str] = None) -> str:
    """Helper to query the traveler's next Google Calendar event dynamically starting after flight landing."""
    try:
        from backend.src.mcp.tools.config import get_service
        from datetime import datetime, timezone
        service = get_service()
        
        # Filter meetings starting after the flight lands (Strategy 1)
        time_min = landing_time_iso if landing_time_iso else datetime.now(timezone.utc).isoformat()
        
        events_result = service.events().list(  # type: ignore
            calendarId='primary',
            timeMin=time_min,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        if events:
            for event in events:
                logger.info(f"[Calendar Event Found] ID: {event['id']} | Summary: {event.get('summary')} | Start: {event['start'].get('dateTime')}")
            return events[0]['id']
    except Exception as e:
        logger.error(f"Error fetching next meeting from Calendar API: {e}")
    # Fallback to the default meeting ID
    # return "3o61p3rpj8jjt7uac6vv0t0gb7"
    return "3a9o753qsql5qubpor6pul14r4"

def start_background_monitoring(airline_code: str, flight_number: str, flight_date: date) -> tuple[str, str, str]:
    """Starts the AmbientOrchestratorAgent loop in the background and returns status info."""
    # 1. Pre-fetch flight details to get the planned scheduled arrival
    try:
        from backend.src.mcp.tools.tools import flight_status_realtime
        flight_info = flight_status_realtime(airline_code, flight_number, flight_date)
        scheduled_arrival = flight_info.Arrival_Time.isoformat()
        status = flight_info.Status
    except Exception as e:
        logger.error(f"Failed to fetch flight status for initial setup: {e}")
        scheduled_arrival = f"{flight_date.isoformat()}T17:45:00"
        status = "unknown"

    # 2. Get the next meeting starting after the scheduled landing time
    meeting_id = get_next_meeting_id(scheduled_arrival)

    from backend.src.travelagent.AmbientOrchestration import AmbientOrchestratorAgent
    agent = AmbientOrchestratorAgent(
        flight_number=flight_number,
        meeting_id=meeting_id,
        flight_airlinecode=airline_code,
        flight_date=flight_date,
        scheduled_arrival=scheduled_arrival,
        user_email="test@company.com",
    )
    
    # Run the polling loop inside FastAPI's running event loop asynchronously
    asyncio.create_task(agent._loop())
    return agent.session_id, status, scheduled_arrival

# ── Routes ────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "GulliverTravels API"}

@app.get("/api/monitor/status")
async def get_monitor_status(session_id: str):
    import sqlite3
    import json
    try:
        conn = sqlite3.connect("orchestrator_state.db")
        cursor = conn.cursor()
        cursor.execute("SELECT state FROM sessions WHERE id = ?;", (session_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            state_data = json.loads(row[0])
            return {"status": "success", "session_id": session_id, "state": state_data}
        else:
            return {"status": "not_found", "session_id": session_id}
    except Exception as e:
        logger.error(f"Error querying monitor status: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/chat")
async def chat(request_body: ChatRequest, token: str = Depends(verify_token)):
    message = request_body.prompt or request_body.message
    if not message:
        raise HTTPException(status_code=400, detail="No message or prompt provided")
    
    try:
        import re
        from datetime import date
        
        # Intercept flight tracking commands: e.g., "monitor UA123", "track F9 2486", etc.
        # Restrict airline code to 2-3 characters containing at least one letter to prevent splitting purely numeric strings
        matches = re.findall(r'\b([A-Za-z]{3}|[A-Za-z][A-Za-z0-9]|[A-Za-z0-9][A-Za-z])\s*(\d{1,4})\b', message)
        match = None
        for m in matches:
            if m[0].lower() not in ["on", "at", "in", "to", "by", "is", "it", "me", "he", "we", "us", "am", "an", "as", "if", "of", "or"]:
                match = m
                break
                
        if match and any(keyword in message.lower() for keyword in ["monitor", "track", "flight", "ambient"]):
            airline_code = match[0].upper()
            flight_number = match[1]
            
            # Detect custom date (YYYY-MM-DD or MM/DD/YYYY)
            date_match = re.search(r'\b(\d{4})[-/](\d{2})[-/](\d{2})\b', message)
            if date_match:
                flight_date = date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
            else:
                # Default to June 1st 2026 or today if not specified
                flight_date = date(2026, 6, 1)
                
            session_id, status, arrival_time = start_background_monitoring(airline_code, flight_number, flight_date)
            
            status_formatted = status.upper().replace("_", " ")
            status_emoji = "🟢" if "ON TIME" in status_formatted else ("🔴" if "DELAYED" in status_formatted or "CANCELLED" in status_formatted else "🟡")
            
            return {
                "response": f"🛫 **Flight Monitoring Activated**\n\n"
                            f"Flight: **{airline_code} {flight_number}** on **{flight_date.isoformat()}**\n"
                            f"Current Status: {status_emoji} **{status_formatted}**\n"
                            f"Arrival Time: **{arrival_time}**\n\n"
                            f"Linked to upcoming calendar event. Ambient monitoring is running in the background.\n"
                            f"Active session ID: `{session_id}`",
                "session_id": session_id,
                "flight_number": flight_number,
                "airline_code": airline_code,
                "status": status,
                "arrival_time": arrival_time
            }

        # Otherwise fall back to standard LLM chat agent
        new_message = types.Content(role="user", parts=[types.Part(text=message)])
        events = runner.run(user_id=request_body.user_id, session_id=request_body.session_id, new_message=new_message)
         
        full_response_text = ""
        for event in events:
            if hasattr(event, 'content') and event.content and event.content.parts:
                # We extract the text from the current event
                current_text = "".join([part.text for part in event.content.parts if part.text])
                if current_text.strip():
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
            model="gemini/gemini-2.5-pro",
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
        
        # Execute the agent using InMemoryRunner
        runner = InMemoryRunner(agent=agent)
        events = runner.run(
            user_id=request.user_id,
            session_id=request.session_id,
            new_message=new_message
        )
        
        transcription = ""
        for event in events:
            if hasattr(event, 'content') and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, 'text') and part.text:
                        transcription += part.text
                        
        return {"transcription": transcription.strip()}
        
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

# ── Entry Point ───────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    ENV = os.getenv("APP_ENV", "dev")

    if ENV == "dev":
        logger.info("🔧 Running in DEV mode — hot reload enabled")
        # Note: using "backend.src.travelagent.main:app" because of the package structure
        uvicorn.run("backend.src.travelagent.main:app", host="0.0.0.0", port=8000, reload=True, workers=1, log_level="debug")
    else:
        logger.info("🚀 Running in PROD mode")
        uvicorn.run("backend.src.travelagent.main:app", host="0.0.0.0", port=8000, reload=False, workers=4, log_level="warning")
