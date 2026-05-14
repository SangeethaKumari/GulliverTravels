"""
check_conflicts.py — Detect scheduling conflicts before booking.

Standalone module imported by book_calendar.py and the AI agent.

Usage (standalone):
    python check_conflicts.py
"""

import datetime
from zoneinfo import ZoneInfo
from config import get_service, TIMEZONE


# ── Core function ─────────────────────────────────────────────────────────────
def check_conflicts(
    service,
    date: str,
    start_time: str,
    end_time: str,
) -> list[dict]:
    """
    Return a list of existing events that overlap with the proposed slot.

    Overlap condition (standard interval intersection):
        existing.start < new.end  AND  existing.end > new.start

    Args:
        service    : authenticated Google Calendar service
        date       : YYYY-MM-DD
        start_time : HH:MM  (24-hour)
        end_time   : HH:MM  (24-hour)

    Returns:
        List of dicts: event_id, title, start (HH:MM), end (HH:MM)
        Empty list means no conflicts.
    """
    tz        = ZoneInfo(TIMEZONE)
    new_start = datetime.datetime.strptime(
        f"{date} {start_time}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=tz)
    new_end   = datetime.datetime.strptime(
        f"{date} {end_time}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=tz)

    # Fetch all events for the day
    day_start = datetime.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
    day_end   = day_start + datetime.timedelta(days=1)

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    conflicts = []
    for e in result.get("items", []):
        # Skip all-day events (they have "date" key, not "dateTime")
        if "dateTime" not in e["start"]:
            continue

        ev_start = datetime.datetime.fromisoformat(e["start"]["dateTime"])
        ev_end   = datetime.datetime.fromisoformat(e["end"]["dateTime"])

        if ev_start < new_end and ev_end > new_start:
            conflicts.append({
                "event_id": e["id"],
                "title":    e.get("summary", "No title"),
                "start":    ev_start.strftime("%H:%M"),
                "end":      ev_end.strftime("%H:%M"),
            })

    return conflicts


def has_conflict(service, date: str, start_time: str, end_time: str) -> bool:
    """Convenience boolean wrapper around check_conflicts."""
    return len(check_conflicts(service, date, start_time, end_time)) > 0


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    service = get_service()

    print("\n🔍  Check for Scheduling Conflicts")
    print("─" * 40)
    date       = input("Date (YYYY-MM-DD): ").strip()
    start_time = input("Start (HH:MM)    : ").strip()
    end_time   = input("End   (HH:MM)    : ").strip()

    conflicts = check_conflicts(service, date, start_time, end_time)

    if not conflicts:
        print(f"\n✅ No conflicts found for {date} {start_time}–{end_time}. Slot is free!")
    else:
        print(f"\n⚠️  {len(conflicts)} conflict(s) found on {date} between {start_time}–{end_time}:")
        for c in conflicts:
            print(f"   • {c['title']}  ({c['start']} – {c['end']})")


if __name__ == "__main__":
    main()
