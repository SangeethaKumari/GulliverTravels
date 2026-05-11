"""
list_calendar.py — List, search, and filter Google Calendar events.

Usage (standalone):
    python list_calendar.py
"""

import datetime
from zoneinfo import ZoneInfo
from config import get_service, TIMEZONE


# ── Core function ─────────────────────────────────────────────────────────────
def list_events(
    service,
    date: str        = None,
    days_ahead: int  = 7,
    max_results: int = 20,
    search: str      = None,
) -> list[dict]:
    """
    List calendar events in a date range.

    Args:
        service     : authenticated Google Calendar service
        date        : start date YYYY-MM-DD (defaults to today)
        days_ahead  : how many days forward to fetch (default 7)
        max_results : max number of events to return
        search      : optional keyword to filter by title

    Returns:
        list of event dicts with event_id, title, start, end,
        description, location, attendees
    """
    tz  = ZoneInfo(TIMEZONE)
    now = datetime.datetime.now(tz)

    if date:
        time_min = datetime.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
    else:
        time_min = now

    time_max = time_min + datetime.timedelta(days=days_ahead)

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
            q=search,          # Google Calendar supports keyword search via 'q'
        )
        .execute()
    )

    events = []
    for e in result.get("items", []):
        start = e["start"].get("dateTime", e["start"].get("date"))
        end   = e["end"].get("dateTime",   e["end"].get("date"))
        events.append({
            "event_id":    e["id"],
            "title":       e.get("summary", "No title"),
            "start":       start,
            "end":         end,
            "description": e.get("description", ""),
            "location":    e.get("location", ""),
            "attendees":   [a["email"] for a in e.get("attendees", [])],
        })

    return events


def list_today(service) -> list[dict]:
    """Convenience: list only today's events."""
    today = datetime.datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
    return list_events(service, date=today, days_ahead=1)


def list_week(service) -> list[dict]:
    """Convenience: list this week's events."""
    return list_events(service, days_ahead=7)


def list_month(service) -> list[dict]:
    """Convenience: list this month's events."""
    return list_events(service, days_ahead=30, max_results=50)


# ── Pretty print helper ───────────────────────────────────────────────────────
def print_events(events: list[dict], heading: str = "Events") -> None:
    print(f"\n📆  {heading}  ({len(events)} found)")
    print("─" * 55)
    if not events:
        print("   No events found.")
        return
    for e in events:
        print(f"  📌 {e['title']}")
        print(f"     🕐 {e['start']}  →  {e['end']}")
        if e["location"]:
            print(f"     📍 {e['location']}")
        if e["attendees"]:
            print(f"     👥 {', '.join(e['attendees'])}")
        print(f"     🆔 {e['event_id']}")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    service = get_service()

    print("\n📋  List Calendar Events")
    print("─" * 40)
    print("1. Today's events")
    print("2. This week's events")
    print("3. This month's events")
    print("4. Custom date range")
    print("5. Search by keyword")

    choice = input("\nChoice (1-5): ").strip()

    if choice == "1":
        events = list_today(service)
        print_events(events, "Today's Events")

    elif choice == "2":
        events = list_week(service)
        print_events(events, "This Week's Events")

    elif choice == "3":
        events = list_month(service)
        print_events(events, "This Month's Events")

    elif choice == "4":
        date      = input("Start date (YYYY-MM-DD): ").strip()
        days      = input("Days ahead (default 7) : ").strip()
        days_int  = int(days) if days.isdigit() else 7
        events    = list_events(service, date=date, days_ahead=days_int)
        print_events(events, f"Events from {date} ({days_int} days)")

    elif choice == "5":
        keyword = input("Search keyword: ").strip()
        events  = list_events(service, days_ahead=30, search=keyword)
        print_events(events, f"Events matching '{keyword}'")

    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
