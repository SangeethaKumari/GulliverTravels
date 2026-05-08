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


if __name__ == "__main__":
    uvicorn.run("travelagent.companion.api:app", host="0.0.0.0", port=8000,
                reload=False, log_level="info")
