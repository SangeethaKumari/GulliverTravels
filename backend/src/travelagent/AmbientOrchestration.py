"""
Ambient Travel Companion — Orchestrator Agent

What's here:
  - DatabaseSessionService  → state survives restarts (from your existing code)
  - delay_history tracking  → appended each cycle (from your existing code)
  - sense-think-act cycle   → calls sub-agents, computes adjusted_p (from your existing code)
  - action_taken guard      → email sent only once (from previous iteration)
  - clean polling loop      → exits on landed / cancelled / Ctrl-C

Set POLL_INTERVAL_SECONDS = 10 for demos; 300 for real use.
"""

from google.adk.evaluation import conversation_scenarios
from google.adk.evaluation import conversation_scenarios
from alembic.autogenerate.compare import server_defaults
import asyncio
import json
import os
import dotenv
dotenv.load_dotenv()
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.sessions.database_session_service import DatabaseSessionService
from google.genai import types

# Sub-agents
from backend.src.travelagent.subagents.FlightAgent.agent import root_agent as FlightAgent
# FIX: Ensure CalendarAgent is imported for the email tool dispatch
from backend.src.travelagent.subagents.CalendarAgent.calendar_agent import CalendarAgent
from backend.src.mcp.tools.flightpydantic import FlightStatusRealtime

# ── Your existing MCP tools ────────────────────────────────────────────────────
from backend.src.mcp.fastmcp_server import get_weather, estimate_route, get_calendar


from backend.src.travelagent.dspyoptimizer import NotificationComposer

import litellm
#litellm._turn_on_debug()

POLL_INTERVAL_SECONDS = 18   # ← set to 30 for demos
APP_NAME = "ambient_travel_companion"
#monitor AA 456 on 2026-06-01
#monitor AA 2486 on 2026-06-01

_composer = NotificationComposer()
_base_dir = os.path.dirname(os.path.abspath(__file__))
_composer.load(os.path.join(_base_dir, "optimized_notification_composer.json"))

class AmbientOrchestratorAgent:
    """
    Polls flight status on a fixed interval.
    On delay ≥ 30 min: runs the agent committee, computes adjusted probability,
    and sends one email if a meeting is impacted. Persists all state to SQLite.
    """

    def __init__(
        self,
        flight_number: str,
        meeting_id: str,
        flight_airlinecode: str,
        flight_date: date,
        scheduled_arrival: str,       # ISO string  e.g. "2026-06-29T17:45:00"
        user_email: str,
    ):
        self.flight_number      = flight_number
        self.meeting_id         = meeting_id
        self.flight_airlinecode = flight_airlinecode
        self.flight_date        = flight_date
        self.scheduled_arrival  = datetime.fromisoformat(scheduled_arrival)
        self.user_email         = user_email
        self.agent_name         = "AmbientTravelOrchestrator"
        self.session_id         = f"session_{flight_number}_{meeting_id}"

        # ── Persistent SQL session service (your original approach) ────────────
        db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///orchestrator_state.db")
        self.session_service = DatabaseSessionService(db_url=db_url)

        self.initial_state = {
            "is_monitoring_active": False,
            "delay_history": [],
            "current_status": "unknown",
            "email_sent": False,          # guard lives in DB — survives restarts
        }

    # ── Session helpers ────────────────────────────────────────────────────────

    async def _get_or_init_session(self) -> Session:
        session = await self.session_service.get_session(
            app_name=self.agent_name,
            user_id="system_orchestrator",
            session_id=self.session_id,
        )
        if session is not None:
            return session
        await self.session_service.create_session(
            app_name=self.agent_name,
            user_id="system_orchestrator",
            session_id=self.session_id,
        )
        # Fetch the freshly created session so we always return a real object
        session = await self.session_service.get_session(
            app_name=self.agent_name,
            user_id="system_orchestrator",
            session_id=self.session_id,
        )
        if session is None:
            session = Session(
                id=self.session_id,
                app_name=self.agent_name,
                user_id="system_orchestrator",
                state=self.initial_state,
            )
        return session

    async def _sync(self, changes: Dict[str, Any]):
        """Commit a state delta to the database via an ADK Event."""
        session = await self._get_or_init_session()
        await self.session_service.append_event(
            session=session,
            event=Event(author="system", actions={"state_delta": changes}),
        )

    # ── Entry point ────────────────────────────────────────────────────────────

    def start(self):
        """Blocking entry point — call this from __main__."""
        asyncio.run(self._loop())

    # ── Main polling loop ──────────────────────────────────────────────────────

    MAX_POLLS = 6        # hard ceiling
    MONITORING_WINDOW_HOURS = 72  # stop if scheduled arrival is this far in the past

    async def _heartbeat(self):
        while True:
            print(".", end="", flush=True)
            await asyncio.sleep(1)

    async def _loop(self):
        heartbeat_task = asyncio.create_task(self._heartbeat())
        await self._sync({"is_monitoring_active": True, "current_status": "active"})
        print(f"[{self.agent_name}] Monitoring {self.flight_number}. "
              f"Polling every {POLL_INTERVAL_SECONDS}s. Ctrl-C to stop.\n")

        poll_count = 0
        stop_reason = None

        try:
            while True:
                # ── Exit 1: hard poll ceiling ─────────────────────────────────
                if poll_count >= self.MAX_POLLS:
                    stop_reason = f"max polls ({self.MAX_POLLS}) reached"
                    break

                # ── Exit 2: monitoring window expired ─────────────────────────
                current_time_la = datetime.now(ZoneInfo("America/Los_Angeles"))
                scheduled_arrival_la = self.scheduled_arrival.replace(tzinfo=ZoneInfo("America/Los_Angeles")) if self.scheduled_arrival.tzinfo is None else self.scheduled_arrival.astimezone(ZoneInfo("America/Los_Angeles"))
                hours_elapsed = (current_time_la - scheduled_arrival_la).total_seconds() / 3600
                if hours_elapsed > self.MONITORING_WINDOW_HOURS:
                    stop_reason = f"window expired ({self.MONITORING_WINDOW_HOURS}h past scheduled arrival)"
                    break

                poll_count += 1
                print(f"\n── Poll #{poll_count}/{self.MAX_POLLS} {'─' * 36}")
                print(f"[{self.agent_name}] [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Polling flight status (Interval: {POLL_INTERVAL_SECONDS}s)...")

                session = await self._get_or_init_session()
                should_stop, stop_reason = await self._sensing_cycle(session)

                # ── Exit 3: flight landed or cancelled ────────────────────────
                if should_stop:
                    break

                print(f"[{self.agent_name}] Sleeping {POLL_INTERVAL_SECONDS}s ...\n")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            stop_reason = "stopped by user (Ctrl-C)"

        finally:
            print(f"\n[{self.agent_name}] Loop ended — {stop_reason}")
            await self._sync({"is_monitoring_active": False, "stop_reason": stop_reason})
            heartbeat_task.cancel()  # Clean it up when the loop ends

    # ── Sensing cycle ──────────────────────────────────────────────────────────

    async def _sensing_cycle(self, session: Session) -> tuple[bool, str]:
        """
        Sense → Think → Act for one poll cycle.
        Returns True when the loop should stop (landed / cancelled).
        """

        # ── 1. SENSE: flight status via FlightAgent ────────────────────────────
        flight_info, current_status, actual_arrival_str = await self._fetch_flight_status()
        await self._sync({"current_status": current_status})

        print(f"\n📢 [SENSE] Flight Status: {current_status.upper()}")
        if flight_info:
            print(f"   • Airline           : {flight_info.airline_code} | Flight: {flight_info.flight_number}")
            print(f"   • Route             : {flight_info.Departure_Airport} ➔ {flight_info.Arrival_Airport}")
            print(f"   • Departure Time    : {flight_info.Departure_Time}")
            print(f"   • Scheduled Arrival : {self.scheduled_arrival}")
            print(f"   • Estimated Arrival : {flight_info.Arrival_Time}")

        if current_status == "cancelled":
            self._log_ledger("cancellation", 0, None, None, 1.0)
            
            # Send cancellation email alert
            email_already_sent = session.state.get("email_sent", False)
            if not email_already_sent:
                calendar_info = get_calendar(self.meeting_id)
                await self._send_email(flight_info, "cancelled", 0.0, calendar_info)
                await self._sync({"email_sent": True})
            else:
                print("   • Cancellation email already sent. Skipping.")
                
            await self._sync({"is_monitoring_active": False})
            print("🛑 [ACT] Flight cancelled. Stopping monitor.")
            return True, "flight cancelled"

        if current_status == "landed":
            print("🎉 [ACT] Flight landed. Stopping monitor.")
            return True, "flight landed"

        if current_status == "on_time":
            print("✅ [COMPUTE] Flight is on time. Remaining quiet.")
            # Sync 0 delay to the history so the UI dashboard registers active polling progress
            old_history = list(session.state.get("delay_history", []))
            delay_history = list(old_history)
            delay_history.append(0)
            await self._sync({"delay_history": delay_history})
            return False, ""

        # ── 2. COMPUTE delay minutes ───────────────────────────────────────────
        raw_delay = self._compute_delay_minutes(actual_arrival_str)

        # Append to persistent history (your original pattern)
        old_history = list(session.state.get("delay_history", []))
        delay_history = list(old_history)
        delay_history.append(raw_delay)
        await self._sync({"delay_history": delay_history})

        print(f"📈 [HISTORY UPDATE]:")
        print(f"   • Loaded Previous History from DB : {old_history}")
        print(f"   • Appending New Delay             : {raw_delay} min")
        print(f"   • Updated History (saved to DB)   : {delay_history}")

        if raw_delay < 30:
            print(f"🤫 [COMPUTE] Delay ({raw_delay} min) is under the 30-min threshold. Remaining quiet.")
            return False, ""

        # ── 3. GATHER context ──────────────────────────────────────────────────
        weather_info  = get_weather(lat=40.7128, lon=-74.0060)
        route_info    = estimate_route(origin="airport", destination="meeting_address")
        calendar_info = get_calendar(self.meeting_id)

        # ── 4. THINK: committee agents ─────────────────────────────────────────
        # Guard clause ensures flight_info is completely valid and not None
        if flight_info is None:
            print(f"⚠️ [THINK] No flight info available. Skipping analysis.")
            return False, "Missing flight information"

        time_out   = await self._call_time_agent(flight_info, route_info)
        risk_out   = await self._call_risk_agent(weather_info, delay_history)
        impact_out = await self._call_impact_agent(calendar_info)

        p              = time_out["p_arrive_by_deadline"]
        multiplier     = risk_out["delay_multiplier"]
        meeting_weight = impact_out["meeting_weight"]

        # Adjusted probability formula from the spec
        adjusted_p = max(0.0, p - (0.2 * (multiplier - 1.0)))
        print(f"🧠 [THINK] Committee Decision-Making:")
        print(f"   • On-time Probability (P) : {p:.0%}")
        print(f"   • Risk Multiplier         : {multiplier:.2f}x")
        print(f"   • Meeting Weight          : {meeting_weight:.2f}")
        print(f"   • Adjusted Probability    : {adjusted_p:.0%} (Reschedule Threshold: < 60%)")

        # ── 5. ACT ────────────────────────────────────────────────────────────
        email_already_sent = session.state.get("email_sent", False)

        if adjusted_p < 0.60 or (raw_delay >= 90 and meeting_weight > 0.7):
            print(f"🚨 [ACT] Critical threshold reached! Initiating negotiation.")
            self._log_ledger("initiate_negotiation", raw_delay, adjusted_p, meeting_weight, multiplier)
            if not email_already_sent:
                # FIX: Explicitly cast float raw_delay to int to perfectly fulfill signature requirements
                await self._send_email(flight_info, int(raw_delay), adjusted_p, calendar_info)
                await self._sync({"email_sent": True})
            else:
                print(f"   • Email notification already sent. Skipping dispatch.")

        elif adjusted_p <= 0.85 and meeting_weight > 0.5:
            print(f"⚠️ [ACT] Soft heads-up threshold reached. Notifying user.")
            self._log_ledger("soft_heads_up", raw_delay, adjusted_p, meeting_weight, multiplier)

        else:
            print(f"🤫 [ACT] Within acceptable limits. Silent cycle.")

        return False, ""  # keep polling

    # ── Flight status fetch ────────────────────────────────────────────────────

    async def _fetch_flight_status(self) -> tuple[FlightStatusRealtime | None, str, str]:
        """Calls FlightAgent and returns the Pydantic object + extracted fields."""
        date_str = (
            self.flight_date.strftime("%Y-%m-%d")
            if isinstance(self.flight_date, date)
            else self.flight_date
        )
        prompt = (
            f"Get the flight status for airline code {self.flight_airlinecode}, "
            f"flight number {self.flight_number}, and date {date_str}."
        )
        runner = InMemoryRunner(agent=FlightAgent)
        runner.auto_create_session = True

        flight_info: FlightStatusRealtime | None = None

        async for event in runner.run_async(
            user_id="system",
            session_id=self.meeting_id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        ):
            if hasattr(event, "content") and event.content and event.content.parts:
                for part in event.content.parts:
                    # Log the parts for visibility/debugging
                    if hasattr(part, "text") and part.text:
                        print(f"[{self.agent_name}] [DEBUG] Model text part: {part.text.strip()}")
                    if hasattr(part, "function_call") and part.function_call:
                        print(f"[{self.agent_name}] [DEBUG] Model tool call: {part.function_call.name} args: {part.function_call.args}")
                    
                    # ADK surfaces tool output as a function_response part
                    if hasattr(part, "function_response") and part.function_response:
                        raw = part.function_response.response or {}
                        #print(f"[{self.agent_name}] [DEBUG] Tool response received: {part.function_response.name} -> {raw}")
                        
                        # If the response is wrapped by FastMCP v2 structure, unwrap it
                        data_source = raw
                        if "structuredContent" in raw and isinstance(raw["structuredContent"], dict):
                            data_source = raw["structuredContent"]
                        
                        # 1. Safely extract values from data_source, supporting both Title_Case and snake_case variants
                        dep_air = data_source.get("departure_airport") or data_source.get("Departure_Airport") or ""
                        arr_air = data_source.get("arrival_airport") or data_source.get("Arrival_Airport") or ""
                        dep_time_str = data_source.get("departure_time") or data_source.get("Departure_Time") or ""
                        arr_time_str = data_source.get("arrival_time") or data_source.get("Arrival_Time") or ""
                        airline = data_source.get("airline_code") or data_source.get("airline") or ""
                        flight_num = data_source.get("flight_number") or data_source.get("flight_nubmer") or ""
                        status_val = data_source.get("status") or data_source.get("Status") or ""


                        # Helper to parse date/datetime string into a date object
                        def parse_to_datetime(val: Any) -> datetime:
                            if isinstance(val, datetime):
                                return val
                            if isinstance(val, date):
                                return datetime(val.year, val.month, val.day)
                            val_str = str(val or "").strip()
                            if not val_str:
                                return datetime.now()
                            try:
                                return datetime.fromisoformat(val_str)          # ← keeps 18:15:00
                            except ValueError:
                                try:
                                    return datetime.strptime(val_str, "%Y%m%d")
                                except ValueError:
                                    return datetime.now()
                        dep_time = parse_to_datetime(dep_time_str)
                        arr_time = parse_to_datetime(arr_time_str)
                        print(f"[DEBUG] dep_time: {dep_time}, arr_time: {arr_time}")
                        

                        # 2. Check if any crucial keys are completely missing or empty
                        if dep_air and arr_air and dep_time_str and arr_time_str and airline and flight_num and status_val:
                            flight_info = FlightStatusRealtime(
                                Departure_Airport=str(dep_air),
                                Departure_Time=dep_time,
                                Arrival_Airport=str(arr_air),
                                Arrival_Time=arr_time,
                                airline_code=str(airline),
                                flight_number=str(flight_num),
                                Status=str(status_val)
                            )
                            
                        else:
                            print(f"[{self.agent_name}] Error: Raw data is missing required fields.")
                            flight_info = None

        # FIX: Relocated processing checks completely outside the event looping blocks
        if flight_info is None:
            print(f"[{self.agent_name}] FlightAgent returned no structured response.")
            return None, "on_time", ""

        current_status     = flight_info.Status.lower().strip()
        actual_arrival_str = (
            flight_info.Arrival_Time.isoformat()
            if isinstance(flight_info.Arrival_Time, date)
            else str(flight_info.Arrival_Time)
        )

        return flight_info, current_status, actual_arrival_str

    # ── Delay computation ──────────────────────────────────────────────────────

    def _compute_delay_minutes(self, actual_arrival_str: str) -> int:
        if actual_arrival_str and actual_arrival_str != "--":
            try:
                actual = datetime.fromisoformat(actual_arrival_str)
                delta  = actual - self.scheduled_arrival
                delay_mins = max(0, int(delta.total_seconds() / 60))
                print(f"⏱️ [CALCULATING DELAY]:")
                print(f"   • Actual Arrival (Est) : {actual}")
                print(f"   • Scheduled Arrival    : {self.scheduled_arrival}")
                print(f"   • Subtract Equation    : {actual.strftime('%H:%M:%S')} - {self.scheduled_arrival.strftime('%H:%M:%S')}")
                print(f"   • Resulting Difference : {delta} ({delay_mins} minutes)")
                return delay_mins
            except Exception as e:
                print(f"[{self.agent_name}] Date parse error: {e}. Using 30 min fallback.")
        return 30

    # ── Email dispatch ────────────────────────────────────────────────────────
    async def _send_email(self, flight_info, delay_minutes, adjusted_p, calendar_info=None):
        # 1. Resolve attendees and times dynamically if calendar_info is available
        attendees = ["meeting attendees"]
        meeting_weight = "high"
        
        is_cancelled = (delay_minutes == "cancelled")
        delay_val = 0 if is_cancelled else int(delay_minutes)
        
        proposed_times = [
            (datetime.now() + timedelta(minutes=delay_val)).strftime("%I:%M %p"),
            (datetime.now() + timedelta(minutes=delay_val + 30)).strftime("%I:%M %p"),
        ]
        
        if calendar_info:
            # 1. Safely pull the attendees list from the calendar dictionary
            raw_attendees = calendar_info.get("attendees", [])
            # 2. Append the items directly if they are already email strings
            if isinstance(raw_attendees, list):
                for a in raw_attendees:
                    if isinstance(a, str):
                        attendees.append(a)  # Just take the string directly!
                    elif isinstance(a, dict):
                        attendees.append(a.get("email", "attendee"))
            if calendar_info.get("is_flexible") is not None:
                meeting_weight = "low" if calendar_info.get("is_flexible") else "high"
            
            start_str = calendar_info.get("start")
            if start_str:
                try:
                    tz = ZoneInfo("America/Los_Angeles")
                    start_dt = datetime.fromisoformat(start_str).astimezone(tz)
                    proposed_times = [
                        (start_dt + timedelta(minutes=delay_val)).strftime("%I:%M %p"),
                        (start_dt + timedelta(minutes=delay_val + 30)).strftime("%I:%M %p"),
                    ]
                except Exception:
                    pass

        # 2. Construct the scenario for the DSPy optimizer
        scenario = {
            "delay_duration":  "cancelled" if is_cancelled else delay_val,
            "meeting_weight":  meeting_weight,
            "attendees":       attendees,
            "weather":         "unknown",
            "current_time":    datetime.now().strftime("%I:%M %p"),
            "proposed_times":  proposed_times
        }   
        
        # 3. Call DSPy composer with a strict 15-second network timeout guard
        try:
            print(f"\n[{self.agent_name}] Sending payload to DSPy cloud module (15s timeout maximum)...")
            #email_body = _composer(scenario)
            # Wrap the background thread runner in a strict asyncio timeout
            prediction = await asyncio.wait_for(
                asyncio.to_thread(_composer, scenario), 
                timeout=15.0
            )
            
            if hasattr(prediction, "notification"):
                email_body = prediction.notification
            elif isinstance(prediction, dict) and "notification" in prediction:
                email_body = prediction["notification"]
            else:
                email_body = str(prediction) # Fallback if it's already a string
            
            print(f"[DSPy Optimized Notification (Extracted String Only)]:\n{email_body}")

            print(f"[DSPy Optimized Notification]:\n{email_body}")
        except asyncio.TimeoutError:
            print(f"⚠️ [{self.agent_name}] DSPy cloud module timed out after 15 seconds! Dropping connection.")
            print(f"[{self.agent_name}] Activating local backup text template immediately to preserve loop uptime.")
            email_body = '''Good afternoon, I regret to inform you that due to heavy rain and unexpected road closures, 
            I will be delayed by approximately 90 minutes and will not be able to attend the meeting. I can join remotely 
            today if that is preferable. Alternatively, we can resume the discussion tomorrow at 3:30 PM. 
            Please let me know which option best accommodates your schedules. 
            Thank you for your understanding and flexibility.'''
        except Exception as e:
            print(f"[{self.agent_name}] DSPy composer error: {e}. Using structural text fallback.")
            email_body = '''Good afternoon, I regret to inform you that due to heavy rain and unexpected road closures, ...'''

        # 4. Reschedule event using CalendarAgent and update description with the email body
        start_str = calendar_info.get("start") if calendar_info else None
        end_str = calendar_info.get("end") if calendar_info else None
        
        if is_cancelled:
            prompt = (
                f"Edit event {self.meeting_id}. "
                f"Since the flight was cancelled, move the meeting to tomorrow at the same time or cancel it entirely. "
                f"Update the description to say: {email_body}"
            )
        elif start_str and end_str:
            try:
                tz = ZoneInfo("America/Los_Angeles")
                start_dt = datetime.fromisoformat(start_str).astimezone(tz)
                end_dt = datetime.fromisoformat(end_str).astimezone(tz)
                new_start = start_dt + timedelta(minutes=delay_val)
                new_end = end_dt + timedelta(minutes=delay_val)
                prompt = (
                    f"Edit event {self.meeting_id}. "
                    f"Set start to {new_start.strftime('%H:%M')} and end to {new_end.strftime('%H:%M')} on {new_start.strftime('%Y-%m-%d')}. "
                    f"Update the description to say: {email_body}"
                )
            except Exception:
                prompt = (
                    f"Edit event {self.meeting_id}. "
                    f"Delay the start and end time by {delay_val} minutes. "
                    f"Update the description to say: {email_body}"
                )
        else:
            prompt = (
                f"Edit event {self.meeting_id}. "
                f"Delay the start and end time by {delay_val} minutes. "
                f"Update the description to say: {email_body}"
            )
        
        loop = asyncio.get_running_loop()
        agent = CalendarAgent()
        response = await loop.run_in_executor(None, agent.execute, prompt)
        print(f"[CalendarAgent] {response}")
    
    
    
    
    
    async def _send_email_old(self, flight_info: FlightStatusRealtime, delay_minutes: int, adjusted_p: float):
        """Delegates email composition + send to CalendarAgent."""
        prompt = (
            f"Draft an email to the attendees of meeting {self.meeting_id}. "
            f"Flight {flight_info.airline_code}{flight_info.flight_number} "
            f"from {flight_info.Departure_Airport} to {flight_info.Arrival_Airport} "
            f"is delayed by {delay_minutes} minutes. "
            f"New estimated arrival: {flight_info.Arrival_Time}. "
            f"Probability of on-time arrival is {adjusted_p:.0%}. "
            "Apologise briefly, state the delay, and propose rescheduling by 1 hour."
        )
        agent = CalendarAgent()
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, agent.execute, prompt)
        print(f"[CalendarAgent] {response}")
        
    async def _send_email_old2(self, flight_info: FlightStatusRealtime, delay_minutes: int, adjusted_p: float, calendar_info: Dict[str, Any]):
        """Reschedules the meeting by 1 hour — Google Calendar emails attendees automatically."""
        start_str = calendar_info.get("start")
        end_str = calendar_info.get("end")
        if start_str and end_str:
            try:
                start_dt = datetime.fromisoformat(start_str)
                end_dt = datetime.fromisoformat(end_str)
                new_start = start_dt + timedelta(hours=1)
                new_end = end_dt + timedelta(hours=1)
                prompt = (
                    f"Edit event {self.meeting_id}. "
                    f"Set start to {new_start.strftime('%H:%M')} and end to {new_end.strftime('%H:%M')} on {new_start.strftime('%Y-%m-%d')}. "
                    f"Update the description to say: Flight {flight_info.airline_code}"
                    f"{flight_info.flight_number} is delayed by {delay_minutes} minutes."
                )
            except Exception:
                prompt = (
                    f"Edit event {self.meeting_id}. "
                    f"Delay the start and end time by 1 hour. "
                    f"Update the description to say: Flight {flight_info.airline_code}"
                    f"{flight_info.flight_number} is delayed by {delay_minutes} minutes."
                )
        else:
            prompt = (
                f"Edit event {self.meeting_id}. "
                f"Delay the start and end time by 1 hour. "
                f"Update the description to say: Flight {flight_info.airline_code}"
                f"{flight_info.flight_number} is delayed by {delay_minutes} minutes."
            )
        loop = asyncio.get_running_loop()
        agent = CalendarAgent()
        response = await loop.run_in_executor(None, agent.execute, prompt)
        print(f"[CalendarAgent] {response}")
        # ── Committee agent stubs (replace with real AgentTool calls) ─────────────

    async def _call_time_agent(self, flight_info: FlightStatusRealtime, route_info: Dict) -> Dict[str, Any]:
       # TODO: wire to your TimeAgent
        return {"p_arrive_by_deadline": 0.78}

    async def _call_time_agent_v1(self, flight_info: FlightStatusRealtime, route_info: Dict) -> Dict[str, Any]:
        # 1. Adapt flight_info to the dictionary format expected by TimeAgent.assess
        flight_dict = {
            "currentStatus": flight_info.Status,
            "estimatedLanding": flight_info.Arrival_Time.isoformat()
        }
        
        # 2. Adapt route_info to the format expected by TimeAgent.assess
        drive_min = route_info.get("baseline_drive_minutes", 45)
        route_dict = {
            "durationSeconds": drive_min * 60,
            "durationInFreeFlowSeconds": drive_min * 60
        }
        
        # 3. Retrieve calendar info to parse the meeting start time dynamically
        calendar_info = get_calendar(self.meeting_id)
        start_str = calendar_info.get("start")
        if start_str:
            try:
                meeting_start = datetime.fromisoformat(start_str)
            except Exception:
                meeting_start = self.scheduled_arrival + timedelta(hours=2)
        else:
            meeting_start = self.scheduled_arrival + timedelta(hours=2)
            
        # 4. Instantiate and call the TimeAgent
        from backend.src.travelagent.subagents.TimeAgent.time_agent import TimeAgent
        agent = TimeAgent()
        output = agent.assess(
            flight=flight_dict,
            route=route_dict,
            ride_eta_min=15,  # default ride ETA in minutes
            meeting_start=meeting_start,
            flight_number=flight_info.flight_number,
        )
        
        return {"p_arrive_by_deadline": output.p_arrive_by_deadline}

    async def _call_risk_agent(self, weather_info: Dict, history: list) -> Dict[str, Any]:
        # TODO: wire to your RiskAgent
        return {"delay_multiplier": 1.25}

    async def _call_impact_agent(self, calendar_info: Dict) -> Dict[str, Any]:
        # TODO: wire to your ImpactAgent
        return {"meeting_weight": 0.85}

    # ── Decision ledger ────────────────────────────────────────────────────────

    def _log_ledger(self, decision, delay, prob, weight, mult):
        payload = {
            "decision":             decision,
            "delay_minutes":        delay,
            "adjusted_probability": prob,
            "meeting_weight":       weight,
            "delay_multiplier":     mult,
        }
        print(f"\n*** DECISION LEDGER ***\n{json.dumps(payload, indent=2)}\n")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    AmbientOrchestratorAgent(
        flight_number      = "2486",                # Frontier 2486 Non-stop
        meeting_id         = "3a9o753qsql5qubpor6pul14r4",
        flight_airlinecode = "F9",                  # Frontier Airlines
        flight_date        = date(2026, 6, 1),      # Matching your June 1st timeline
        scheduled_arrival  = "2026-06-01T19:34:00", # 7:34 PM Arrival (Forces an active conflict check)
        user_email         = "[EMAIL_ADDRESS]",
    ).start()
