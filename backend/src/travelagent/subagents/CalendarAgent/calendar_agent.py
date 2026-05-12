"""
calendar_agent.py — Agentic AI that understands natural language and
delegates to the appropriate calendar module.

Imports:
    book_calendar    → book_event()
    edit_calendar    → edit_event()
    delete_calendar  → delete_event()
    list_calendar    → list_events()
    check_conflicts  → check_conflicts()

Usage:
    python calendar_agent.py
"""

import json
import datetime
from zoneinfo import ZoneInfo
import google.generativeai as genai

from config import get_service, TIMEZONE, GEMINI_API_KEY
from book_calendar   import book_event
from edit_calendar   import edit_event
from delete_calendar import delete_event
from list_calendar   import list_events, print_events
from check_conflicts import check_conflicts

genai.configure(api_key=GEMINI_API_KEY)


# ── Gemini prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an intelligent calendar assistant.
Parse the user's request into a structured JSON action.

Today      : {today}
Time now   : {now}
Timezone   : {timezone}

Available actions:
  book_event   – create a new event
  edit_event   – modify an existing event (needs event_id)
  delete_event – remove an event (needs event_id)
  list_events  – show upcoming events

Respond ONLY with valid JSON — no markdown fences, no extra text:
{{
  "action": "book_event" | "edit_event" | "list_events" | "delete_event" | "clarify",
  "reasoning": "one line explanation",
  "params": {{
    "title":       "...",
    "date":        "YYYY-MM-DD",
    "start_time":  "HH:MM",
    "end_time":    "HH:MM",
    "description": "optional",
    "attendees":   ["email@example.com"],
    "location":    "optional",
    "event_id":    "required for edit/delete",
    "search":      "keyword for list",
    "days_ahead":  7
  }}
}}
"""


class CalendarAgent:
    """
    Thin AI orchestrator: parse intent → delegate to the right module.
    """

    def __init__(self):
        self.model   = genai.GenerativeModel("gemini-1.5-flash")
        self.history = []   # stores last results for 'book anyway' flow
        try:
            self.service           = get_service()
            self.calendar_connected = True
        except Exception as exc:
            print(f"⚠️  Calendar not connected: {exc}")
            self.calendar_connected = False

    # ── Intent parsing ────────────────────────────────────────────────────────
    def _parse(self, user_input: str, context: str = "") -> dict:
        tz  = ZoneInfo(TIMEZONE)
        now = datetime.datetime.now(tz)
        prompt = SYSTEM_PROMPT.format(
            today=now.strftime("%Y-%m-%d"),
            now=now.strftime("%H:%M"),
            timezone=TIMEZONE,
        )
        if context:
            prompt += f"\n\nPrevious result context:\n{context}"

        raw = self.model.generate_content(f"{prompt}\n\nUser: {user_input}").text.strip()

        # Strip accidental code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())

    # ── Default end time ──────────────────────────────────────────────────────
    @staticmethod
    def _plus_one_hour(start: str) -> str:
        t = datetime.datetime.strptime(start, "%H:%M")
        return (t + datetime.timedelta(hours=1)).strftime("%H:%M")

    # ── Main entry ────────────────────────────────────────────────────────────
    def execute(self, user_input: str) -> str:
        if not self.calendar_connected:
            return "❌ Google Calendar not connected. Set up credentials.json first."

        # ── 'book anyway' shortcut ─────────────────────────────────────────
        if user_input.strip().lower() in ("book anyway", "yes", "proceed", "confirm"):
            last = self.history[-1] if self.history else {}
            if last.get("pending_booking"):
                p      = last["params"]
                result = book_event(self.service, force=True, **p)
                self.history.append(result)
                return (
                    f"✅ Booked (conflict overridden): {result['title']}\n"
                    f"   📅 {result['start']} → {result['end']}\n"
                    f"   🔗 {result['link']}"
                )

        # ── Parse intent via Gemini ────────────────────────────────────────
        context = f"Last result: {json.dumps(self.history[-1])}" if self.history else ""
        try:
            intent = self._parse(user_input, context)
        except Exception as exc:
            return f"❌ Could not parse request: {exc}"

        action    = intent.get("action", "")
        params    = intent.get("params", {})
        reasoning = intent.get("reasoning", "")
        print(f"  💡 {reasoning}  |  🎯 {action}")

        # ── Dispatch ───────────────────────────────────────────────────────
        if action == "book_event":
            date       = params["date"]
            start_time = params["start_time"]
            end_time   = params.get("end_time") or self._plus_one_hour(start_time)

            result = book_event(
                self.service,
                title       = params.get("title", "New Event"),
                date        = date,
                start_time  = start_time,
                end_time    = end_time,
                description = params.get("description", ""),
                attendees   = params.get("attendees", []),
                location    = params.get("location", ""),
            )

            if result["status"] == "conflict":
                lines = [f"⚠️  {result['message']}"]
                for c in result["conflicts"]:
                    lines.append(f"   • {c['title']}  ({c['start']} – {c['end']})")
                lines.append("\nReply 'book anyway' to proceed, or pick a different time.")
                self.history.append({
                    "pending_booking": True,
                    "params": dict(
                        title=params.get("title", "New Event"),
                        date=date, start_time=start_time, end_time=end_time,
                        description=params.get("description", ""),
                        attendees=params.get("attendees", []),
                        location=params.get("location", ""),
                    ),
                })
                return "\n".join(lines)

            self.history.append(result)
            return (
                f"✅ Booked: {result['title']}\n"
                f"   📅 {result['start']} → {result['end']}\n"
                f"   🔗 {result['link']}"
            )

        elif action == "edit_event":
            event_id = params.get("event_id")
            if not event_id and self.history and "event_id" in self.history[-1]:
                event_id = self.history[-1]["event_id"]
            if not event_id:
                return "❌ Need an event_id. List events first to find it."
            result = edit_event(
                self.service,
                event_id    = event_id,
                title       = params.get("title"),
                date        = params.get("date"),
                start_time  = params.get("start_time"),
                end_time    = params.get("end_time"),
                description = params.get("description"),
                location    = params.get("location"),
            )
            self.history.append(result)
            return (
                f"✅ Updated: {result['title']}\n"
                f"   📅 {result['start']} → {result['end']}\n"
                f"   🔗 {result['link']}"
            )

        elif action == "list_events":
            events = list_events(
                self.service,
                date        = params.get("date"),
                days_ahead  = params.get("days_ahead", 7),
                search      = params.get("search"),
            )
            self.history.append({"events": events})
            if not events:
                return "📭 No events found."
            lines = [f"📆 {len(events)} event(s) found:\n"]
            for e in events:
                lines.append(f"  • {e['title']}")
                lines.append(f"    🕐 {e['start']}  →  {e['end']}")
                lines.append(f"    🆔 {e['event_id'][:24]}...")
            return "\n".join(lines)

        elif action == "delete_event":
            event_id = params.get("event_id")
            if not event_id:
                return "❌ Need an event_id to delete. List events first."
            result = delete_event(self.service, event_id)
            self.history.append(result)
            return f"🗑️ Deleted event {event_id[:24]}..."

        elif action == "clarify":
            return f"❓ {reasoning}"

        return f"❌ Unknown action: {action}"


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  🗓️  Agentic AI Calendar Assistant")
    print("=" * 55)
    print("Natural language examples:")
    print("  • Book a team standup tomorrow at 9am for 30 mins")
    print("  • Schedule lunch with Priya on 2026-05-20 at 12:30")
    print("  • Show my events for today")
    print("  • Move the standup to 10am  (after listing events)")
    print("  • Delete the meeting <event_id>")
    print("  • Search for 'review' meetings this week")
    print("  • quit\n")

    agent = CalendarAgent()

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye! 👋")
                break
            response = agent.execute(user_input)
            print(f"\nAssistant:\n{response}\n")
            print("─" * 50)
        except KeyboardInterrupt:
            print("\nGoodbye! 👋")
            break
        except Exception as exc:
            print(f"Error: {exc}")


if __name__ == "__main__":
    main()
