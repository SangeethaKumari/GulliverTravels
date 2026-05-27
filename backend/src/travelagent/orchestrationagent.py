import asyncio
import json
import os
from typing import Any, Dict

# Google ADK ecosystem components for agent loops and database synchronization
from google.adk import Agent
from google.adk.runners import Runner
from google.genai import types

# NATIVE FIX: Import Event along with Session and State
from google.adk.events import Event
from google.adk.sessions import Session, State
from google.adk.sessions.database_session_service import DatabaseSessionService

# Core project MCP tool abstractions

from backend.src.mcp.fastmcp_server import get_weather, estimate_route, get_calendar, flight_status
class AmbientOrchestratorAgent:
    """An autonomous supervisory agent utilizing Google ADK state managemecnt.

    Performs background loop iterations, evaluates committee data streams,
    applies risk adjustments, and commits state transitions directly to a SQL
    database.
    """
#optional input parameters, we can also use default values
    def __init__(self, flight_number: str, meeting_id: str, flight_airlinecode:str, flight_date:str):
        self.agent_name = "AmbientTravelOrchestrator"
        self.flight_number = flight_number
        self.meeting_id = meeting_id
        self.flight_airlinecode = flight_airlinecode
        self.flight_date = flight_date

        # 1. Initialize persistent SQL Storage via Google ADK Session Service
        connection_string = os.getenv(
            "DATABASE_URL", "sqlite+aiosqlite:///orchestrator_state.db"
        )
        self.session_service = DatabaseSessionService(db_url=connection_string)

        # 2. Define the exact schema variables requiring database persistence
        self.initial_state_data = {
            "is_monitoring_active": False,
            "delay_history": [],
            "current_status": "unknown",
        }

        # Unique session row lookup key matching this orchestration target
        self.session_id = f"session_{flight_number}_{meeting_id}"

    async def _get_or_init_session(self) -> Session:
        """Helper to safely fetch or initialize an ADK database session."""
        session = await self.session_service.get_session(
            app_name=self.agent_name,
            user_id="system_orchestrator",
            session_id=self.session_id
        )
        
        if session is not None:
            return session
            
        # If the row is missing from storage, initialize a fresh session object
        new_session = Session(
            id=self.session_id,
            app_name=self.agent_name,
            user_id="system_orchestrator",
            state=self.initial_state_data,
        )
        await self.session_service.create_session(
            app_name=self.agent_name,
            user_id="system_orchestrator",
            session_id=self.session_id)
        return new_session

    async def _sync_state_changes(self, changed_keys: Dict[str, Any]):
        """NATIVE FIX: Commits tracking dictionary changes into the SQL engine

        by building a formal ADK Event container with a state_delta payload.
        """
        # Formulate an event tracking the specific key mutations
        sync_event = Event(
            author="system",
            actions={"state_delta": changed_keys}
        )
        
        session = await self._get_or_init_session()
        # Commit the modification row directly to the database architecture
        await self.session_service.append_event(
            session=session, 
            event=sync_event
        )

    def start_monitoring_loop(self):
        """Activates the persistent background monitoring loop via an async

        bridge.
        """
        asyncio.run(self._main_loop_worker())

    async def _main_loop_worker(self):
        """Asynchronous execution worker handling the persistent loop states."""
        session = await self._get_or_init_session()

        # Use an explicit local attribute check to prevent framework state mismatch crashes
        if getattr(self, "_loop_already_running", False):
            print(
                f"[{self.agent_name}] Warning: Monitoring loop is already spinning."
            )
            return

        # Initialize tracking flags
        self._loop_already_running = True

        await self._sync_state_changes({
            "is_monitoring_active": True,
            "current_status": "active"
        })
        print(
            f"[{self.agent_name}] Agent loop initialized. Persisting to database tracking."
        )

        while True:
            # Refresh session details safely from database
           
            # Should we maintain a new session every time ???
            session = await self._get_or_init_session()

            try:
                #  Force the sensing cycle to run immediately!
                await self._execute_sensing_cycle(session)
                #await self._execute_session_flight_status(session)
            except Exception as e:
                print(
                    f"[{self.agent_name}] Error executing sensing cycle: {e}"
                )

            print(f"[{self.agent_name}] Cycle finished. Sleeping for 30 seconds ...")
            await asyncio.sleep(30)


    async def _execute_session_flight_status(self, session: Session):
        """Runs the main sense-think-act sequence for the current time step."""
        print(
            f"\n[{self.agent_name}] --- Sensing Cycle Execution [Factual Check] ---"
        )

        # 1. PERCEIVE: Query current flight metrics from your MCP tool pipeline
        #def flight_status_realtime(airline_code:str,flight_number:str,input_date):

        flight_info = flight_status(self.flight_airlinecode,self.flight_number,self.flight_date)

        

        # Default value if we can't extract it
        current_status = "on_time"
        #As of now the  tool is returning a string, later we will use the 
        # Pydantic response from the tool    
        # Scan the text block line by line to extract the value
        for line in flight_info.split("\n"):
            if "**Status:**" in line:
                # Splits the line at "**Status:** " and takes everything to the right
                current_status = line.split("**Status:**")[-1].strip()
                break
        
        # FIX: Synchronize current status step
        await self._sync_state_changes({"current_status": current_status})

        # Branch A: Handle complete flight cancellation instantly
        if current_status == "cancelled":
            self._emit_decision_ledger("cancellation", flight_info, session)
            await self._sync_state_changes({"is_monitoring_active": False})
            return

        # Branch B: Handle On-Time flight parameter (Keep a quiet, low-footprint state)
        if current_status == "on_time":
            print(
                f"[{self.agent_name}] Gatekeeper rule: Flight on time. Committing state; remaining silent."
            )
            return

        # 2. GATHER EXTRA CONTEXT: Pull additional environment streams since a delay is verified
        print(
            f"[{self.agent_name}] Factual delay flagged. Gathering route and environmental conditions..."
        )
        

    async def _execute_sensing_cycle(self, session: Session):
        """Runs the main sense-think-act sequence for the current time step."""
        print(
            f"\n[{self.agent_name}] --- Sensing Cycle Execution [Factual Check] ---"
        )

        # 1. PERCEIVE: Query current flight metrics from your MCP tool pipeline
        #def flight_status_realtime(airline_code:str,flight_number:str,input_date):
        
        
        # # 1. Define a specialized Flight agent to act as the "tool"
        

        flight_info = flight_status(self.flight_airlinecode,self.flight_number,self.flight_date)
        # Default value if we can't extract itx
        current_status = "on_time"
        #As of now the  tool is returning a string, later we will use the 
        # Pydantic response from the tool    
        # Scan the text block line by line to extract the value
        for line in flight_info.split("\n"):
            if "**Status:**" in line:
                # Splits the line at "**Status:** " and takes everything to the right
                current_status = line.split("**Status:**")[-1].strip()
                break
            if "**arrival_time:**" in line:
                actual_arrival_str = line.split("**arrival_time:**")[-1].strip()
        
        # FIX: Synchronize current status step
        await self._sync_state_changes({"current_status": current_status})

        # Branch A: Handle complete flight cancellation instantly
        if current_status == "cancelled":
            self._emit_decision_ledger("cancellation", flight_info, session)
            await self._sync_state_changes({"is_monitoring_active": False})
            return

        # Branch B: Handle On-Time flight parameter (Keep a quiet, low-footprint state)
        if current_status == "on_time":
            print(
                f"[{self.agent_name}] Gatekeeper rule: Flight on time. Committing state; remaining silent."
            )
            return
        # ========================================================
        # 🟢 STEP B: REPLACE HARDCODED ROW WITH DYNAMIC LOGIC 
        # ========================================================
        # Only "delayed" flights will ever make it down to this line!
        from datetime import datetime

        if current_status == "delayed" and actual_arrival_str and actual_arrival_str != "--":
            try:
                # Parse the dynamic timestamp from your mock string
                actual_arrival = datetime.fromisoformat(actual_arrival_str)
                
                # Baseline scheduled arrival time target
                scheduled_arrival = datetime.fromisoformat("2026-06-29T17:45:00")
                
                # Calculate the minute delta dynamically
                time_difference = actual_arrival - scheduled_arrival
                raw_delay = int(time_difference.total_seconds() / 60)
            except Exception as e:
                print(f"[{self.agent_name}] Error parsing dates: {e}")
                raw_delay = 30  # Safe fallback if string format anomalies occur
        else:
            raw_delay = 0


        # ========================================================
        # 🔄 STEP C: UPDATE HISTORY ARRAY AND COMMIT CHANGES
        # ========================================================
        updated_history = list(session.state.get("delay_history", []))
        updated_history.append(raw_delay)

        # Sync both values to your SQLite table row
        await self._sync_state_changes({
            "current_status": current_status,
            "delay_history": updated_history
        })

        # 2. GATHER EXTRA CONTEXT: Pull additional environment streams since a delay is verified
        print(
            f"[{self.agent_name}] Factual delay flagged. Gathering route and environmental conditions..."
        )
        weather_info = get_weather(lat=40.7128, lon=-74.0060)
        route_info = estimate_route(
            origin="airport", destination="meeting_address"
        )
        calendar_info = get_calendar(self.meeting_id)

        # Append fresh delay metrics into the database history chain
        raw_delay = 30 if current_status.lower() == "delayed" else 0
        updated_history = list(session.state.get("delay_history", []))
        updated_history.append(raw_delay)
        
        # FIX: Synchronize history modifications
        await self._sync_state_changes({"delay_history": updated_history})

        # 3. THINK: Orchestrate data execution by invoking worker functions
        print(
            f"[{self.agent_name}] Distributing context to downstream specialized sub-agents..."
        )
        time_outputs = self._call_time_agent(flight_info, route_info)
        risk_outputs = self._call_risk_agent(
            weather_info, updated_history
        )
        impact_outputs = self._call_impact_agent(calendar_info)

        p = time_outputs["p_arrive_by_deadline"]
        mult = risk_outputs["delay_multiplier"]
        meeting_weight = impact_outputs["meeting_weight"]

        # 4. COMPUTE: Execute the exact mathematical boundary check from your specification sheet
        adjusted_p = max(0.0, p - (0.2 * (mult - 1.0)))
        print(
            f"[{self.agent_name}] Calculated safety probability: {adjusted_p} (Risk Multiplier: {mult})"
        )

        # 5. ACT: Evaluate limits to declare active mitigations or quiet checkpoints
        if adjusted_p < 0.60 or (raw_delay > 90 and meeting_weight > 0.7):
            print(
                f"[{self.agent_name}] Critical boundary breach. Triggering notification engine."
            )
            self._emit_decision_ledger(
                "initiate_negotiation",
                flight_info,
                session,
                adjusted_p,
                meeting_weight,
                mult,
            )

            # FIX: Synchronize tracking closure
            await self._sync_state_changes({"is_monitoring_active": False})

        elif adjusted_p <= 0.85 and meeting_weight > 0.5:
            print(
                f"[{self.agent_name}] Tight schedule detected. Emitting client soft notification."
            )
            self._emit_decision_ledger(
                "soft_heads_up",
                flight_info,
                session,
                adjusted_p,
                meeting_weight,
                mult,
            )

        else:
            print(
                f"[{self.agent_name}] Parameters evaluated within acceptable limits. Committing silent loop state."
            )

    def _emit_decision_ledger(
        self,
        decision: str,
        flight_info: str,  # Type matches the tool's string output
        session: Session,
        prob: float | None = None,
        weight: float | None = None,
        mult: float = 1.0,
    ):
        """Prepares and logs the formal JSON output format requested by your
        team's specification schema, safely handling string-based tool outputs.
        """
        raw_delay = 0
        
        # Scan the text template lines returned by the flight tool
        for line in flight_info.split("\n"):
            if "**Status:**" in line:
                status_value = line.split("**Status:**")[-1].strip().lower()
                # If the text status confirms a delay, assign a temporary fallback metric 
                # until your team implements numerical minute tracking in the tool text string
                if status_value == "delayed":
                    raw_delay = 45  # Standard threshold placeholder
                break

        payload = {
            "decision": decision,
            "adjusted_probability": prob,
            "delay_minutes": raw_delay,
            "meeting_weight": weight,
            "delay_multiplier": mult,
            "rationale": "Autonomous structural validation cycle executed. Session stored under flight tracking key.",
        }
        print(
            f"\n*** EMITTING COMPLIANT DECISION LEDGER RECORD ***\n{json.dumps(payload, indent=2)}\n"
        )
    # --- Workers (Placeholders targeting your teammates' files inside 'src/agents/') ---
    def _call_time_agent(
        self, flight_info: str, route_info: Dict
    ) -> Dict[str, Any]:
        return {"p_arrive_by_deadline": 0.78}

    def _call_risk_agent(
        self, weather_info: Dict, history: list
    ) -> Dict[str, Any]:
        return {"delay_multiplier": 1.25}

    def _call_impact_agent(self, calendar_info: Dict) -> Dict[str, Any]:
        return {"meeting_weight": 0.85}
