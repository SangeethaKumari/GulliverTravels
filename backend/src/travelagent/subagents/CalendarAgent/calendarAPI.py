"""
api.py — FastAPI REST API exposing each calendar module as endpoints.

Run:
    uvicorn api:app --reload --port 8000

Endpoints:
    GET    /events              → list_calendar
    POST   /events              → book_calendar  (with conflict guard)
    PUT    /events/{event_id}   → edit_calendar
    DELETE /events/{event_id}   → delete_calendar
    GET    /conflicts           → check_conflicts
    POST   /chat                → calendar_agent  (natural language)
    GET    /health
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config          import get_service
from book_calendar   import book_event
from edit_calendar   import edit_event
from delete_calendar import delete_event
from list_calendar   import list_events
from check_conflicts import check_conflicts
from calendar_agent  import CalendarAgent

import datetime

app = FastAPI(title="Agentic Calendar API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared service + agent (stateful for conversation context)
_service = get_service()
_agent   = CalendarAgent()


# ── Request models ────────────────────────────────────────────────────────────
class BookRequest(BaseModel):
    title:       str
    date:        str           # YYYY-MM-DD
    start_time:  str           # HH:MM
    end_time:    str           # HH:MM
    description: str  = ""
    attendees:   list[str] = []
    location:    str  = ""

class EditRequest(BaseModel):
    title:       str  = None
    date:        str  = None
    start_time:  str  = None
    end_time:    str  = None
    description: str  = None
    location:    str  = None

class ChatRequest(BaseModel):
    message: str


# ── /events — list ────────────────────────────────────────────────────────────
@app.get("/events", summary="List upcoming events (list_calendar)")
def api_list_events(
    date:        str = Query(None, description="YYYY-MM-DD start date"),
    days_ahead:  int = Query(7,    description="Days to look ahead"),
    max_results: int = Query(20),
    search:      str = Query(None, description="Keyword filter"),
):
    events = list_events(
        _service,
        date=date,
        days_ahead=days_ahead,
        max_results=max_results,
        search=search,
    )
    return {"count": len(events), "events": events}


# ── /events — book ────────────────────────────────────────────────────────────
@app.post("/events", summary="Book a new event (book_calendar)")
def api_book_event(
    req:   BookRequest,
    force: bool = Query(False, description="Override conflict check"),
):
    result = book_event(
        _service,
        title=req.title, date=req.date,
        start_time=req.start_time, end_time=req.end_time,
        description=req.description, attendees=req.attendees,
        location=req.location, force=force,
    )
    if result["status"] == "conflict":
        raise HTTPException(
            status_code=409,
            detail={
                "message":   result["message"],
                "conflicts": result["conflicts"],
                "hint":      "Add ?force=true to book anyway.",
            },
        )
    return result


# ── /events/{id} — edit ───────────────────────────────────────────────────────
@app.put("/events/{event_id}", summary="Edit an existing event (edit_calendar)")
def api_edit_event(event_id: str, req: EditRequest):
    try:
        result = edit_event(
            _service,
            event_id=event_id,
            title=req.title, date=req.date,
            start_time=req.start_time, end_time=req.end_time,
            description=req.description, location=req.location,
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


# ── /events/{id} — delete ─────────────────────────────────────────────────────
@app.delete("/events/{event_id}", summary="Delete an event (delete_calendar)")
def api_delete_event(
    event_id:         str,
    notify_attendees: bool = Query(True),
):
    try:
        result = delete_event(_service, event_id, notify_attendees=notify_attendees)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


# ── /conflicts — check ────────────────────────────────────────────────────────
@app.get("/conflicts", summary="Check for scheduling conflicts (check_conflicts)")
def api_check_conflicts(
    date:       str = Query(..., description="YYYY-MM-DD"),
    start_time: str = Query(..., description="HH:MM"),
    end_time:   str = Query(..., description="HH:MM"),
):
    conflicts = check_conflicts(_service, date, start_time, end_time)
    return {
        "has_conflict": len(conflicts) > 0,
        "count":        len(conflicts),
        "conflicts":    conflicts,
    }


# ── /chat — AI agent ──────────────────────────────────────────────────────────
@app.post("/chat", summary="Natural language calendar agent (calendar_agent)")
def api_chat(req: ChatRequest):
    response = _agent.execute(req.message)
    return {"response": response}


# ── /health ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":    "ok",
        "timestamp": datetime.datetime.now().isoformat(),
    }
