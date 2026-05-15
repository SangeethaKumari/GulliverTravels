"""Standalone companion API — runs on port 8000 without Google ADK.

Use this for testing the companion orchestration endpoints:

    PYTHONPATH=backend/src python -m travelagent.companion.api

Then:
    curl -X POST http://localhost:8000/companion/run \
         -H "Content-Type: application/json" \
         -d '{"scenario": "B"}'
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import mocks
from .composer import HeuristicComposer
from .orchestrator import Orchestrator
from .scenarios import scenario_A, scenario_B, scenario_C, scenario_D
from .monitor import AmbientOrchestrator
from .persistence import DB
from .timelines import ALL_TIMELINES
import copy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Travel Companion API",
    version="0.2.0",
    description="Ambient Travel Companion — standalone orchestration endpoints",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_SCENARIO_MAP = {
    "A": scenario_A,
    "B": scenario_B,
    "C": scenario_C,
    "D": scenario_D,
}


class CompanionRequest(BaseModel):
    flight_number: str = "UA123"
    user_id: str = "user-1"
    scenario: Optional[str] = None


class ScenarioRequest(BaseModel):
    scenario: str


class TimelineRequest(BaseModel):
    timeline: str = "storm"  # storm | friday | cancel_recovery | landed
    flight_number: str = "UA123"
    user_id: str = "user-1"


class TripStatusRequest(BaseModel):
    trip_id: str


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Travel Companion API"}


@app.post("/companion/scenario")
async def set_scenario(body: ScenarioRequest):
    key = body.scenario.upper()
    factory = _SCENARIO_MAP.get(key)
    if not factory:
        raise HTTPException(400, f"Unknown scenario '{body.scenario}'. Use A/B/C/D.")
    state = factory()
    mocks.set_scenario(state)
    mocks.set_now(datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc))
    return {"scenario": key, "name": state.name}


@app.post("/companion/run")
async def run_companion(body: CompanionRequest):
    if body.scenario:
        key = body.scenario.upper()
        factory = _SCENARIO_MAP.get(key)
        if not factory:
            raise HTTPException(400, f"Unknown scenario '{body.scenario}'.")
        mocks.set_scenario(factory())
        mocks.set_now(datetime(2026, 5, 7, 12, 0, tzinfo=timezone.utc))

    orch = Orchestrator(user_name="Sam", composer=HeuristicComposer())
    result = orch.run_cycle(flight_number=body.flight_number, user_id=body.user_id)

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
            {"channel": n["channel"], "to": n["to"],
             "message": n["message"], "rewards": n["rewards"]}
            for n in result.log.notifications
        ],
        "calendar_updates": result.log.calendar_updates,
        "rides_booked": result.log.rides_booked,
        "rides_cancelled": result.log.rides_cancelled,
    }


@app.get("/companion/tools")
async def list_tools():
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


# ── Ambient Monitoring Endpoints ──────────────────────

@app.post("/companion/timeline")
async def run_timeline(body: TimelineRequest):
    """Simulate a multi-step timeline (e.g. 'storm hits at iteration 7').
    
    Returns per-iteration results showing how the orchestrator reacts
    to state transitions over time — the core ambient agent demo.
    """
    factory = ALL_TIMELINES.get(body.timeline)
    if not factory:
        raise HTTPException(400,
            f"Unknown timeline '{body.timeline}'. "
            f"Available: {list(ALL_TIMELINES.keys())}")

    steps = factory()
    # Deep copy since simulate_timeline mutates step dicts
    steps_copy = [copy.deepcopy(s) for s in steps]

    import uuid
    trip_id = f"trip-{uuid.uuid4().hex[:8]}"
    db = DB(":memory:")
    orch = AmbientOrchestrator(db=db, user_name="Sam",
                                composer=HeuristicComposer())

    results = orch.simulate_timeline(
        trip_id=trip_id,
        flight_number=body.flight_number,
        user_id=body.user_id,
        timeline_steps=steps_copy,
    )

    # Also return persisted data for inspection
    snapshots = db.get_snapshots(trip_id)
    committee_runs = db.get_committee_runs(trip_id)
    actions = db.get_actions(trip_id)
    trip = db.get_trip(trip_id)
    db.close()

    return {
        "trip_id": trip_id,
        "trip_status": trip["status"] if trip else "unknown",
        "timeline": body.timeline,
        "iterations": results,
        "summary": {
            "total_polls": len(results),
            "committee_runs": len(committee_runs),
            "actions_dispatched": len(actions),
            "final_decision": results[-1]["decision"] if results else None,
            "decisions_over_time": [r["decision"] for r in results],
        },
        "persistence": {
            "snapshots": len(snapshots),
            "committee_runs": len(committee_runs),
            "actions": len(actions),
        },
    }


@app.get("/companion/timelines")
async def list_timelines():
    """List available timeline scenarios."""
    return {"timelines": list(ALL_TIMELINES.keys())}


if __name__ == "__main__":
    uvicorn.run("travelagent.companion.api:app", host="0.0.0.0", port=8000,
                reload=False, log_level="info")
