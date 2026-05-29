"""
edit_calendar.py — Update / reschedule existing Google Calendar events.

Usage (standalone):
    python edit_calendar.py
"""

import datetime
from zoneinfo import ZoneInfo
try:
    from backend.src.mcp.tools.config import get_service, TIMEZONE
except ImportError:
    try:
        from .config import get_service, TIMEZONE
    except ImportError:
        from config import get_service, TIMEZONE


# ── Core function ─────────────────────────────────────────────────────────────
def edit_event(
    service,
    event_id: str,
    title: str | None       = None,
    date: str | None        = None,
    start_time: str | None  = None,
    end_time: str | None    = None,
    description: str | None = None,
    location: str | None    = None,
) -> dict:
    """
    Update one or more fields of an existing calendar event.
    Only the fields you pass are changed; everything else stays the same.

    Args:
        service    : authenticated Google Calendar service
        event_id   : Google Calendar event ID
        title      : new title (optional)
        date       : new date YYYY-MM-DD (optional)
        start_time : new start HH:MM (optional)
        end_time   : new end   HH:MM (optional)
        description: new description (optional)
        location   : new location (optional)

    Returns:
        dict with status, event_id, title, start, end, link
    """
    # Fetch the current event
    event = service.events().get(calendarId="primary", eventId=event_id).execute()
    tz    = ZoneInfo(TIMEZONE)

    # ── Apply text field changes ──────────────────────────────────────────────
    if title is not None:
        event["summary"] = title
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location

    # ── Apply date/time changes ───────────────────────────────────────────────
    if date or start_time or end_time:
        existing_start = datetime.datetime.fromisoformat(event["start"]["dateTime"]).astimezone(tz)
        existing_end   = datetime.datetime.fromisoformat(event["end"]["dateTime"]).astimezone(tz)

        use_date  = date       or existing_start.strftime("%Y-%m-%d")
        use_start = start_time or existing_start.strftime("%H:%M")
        use_end   = end_time   or existing_end.strftime("%H:%M")

        new_start = datetime.datetime.strptime(
            f"{use_date} {use_start}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=tz)
        new_end = datetime.datetime.strptime(
            f"{use_date} {use_end}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=tz)

        event["start"] = {"dateTime": new_start.isoformat(), "timeZone": TIMEZONE}
        event["end"]   = {"dateTime": new_end.isoformat(),   "timeZone": TIMEZONE}

    updated = (
        service.events()
        .update(calendarId="primary", eventId=event_id, body=event, sendUpdates="all")
        .execute()
    )

    return {
        "status":   "updated",
        "event_id": event_id,
        "title":    updated["summary"],
        "start":    updated["start"]["dateTime"],
        "end":      updated["end"]["dateTime"],
        "link":     updated.get("htmlLink", ""),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    service = get_service()

    print("\n✏️   Edit a Calendar Event")
    print("─" * 40)
    print("Leave a field blank to keep the existing value.\n")

    event_id    = input("Event ID        : ").strip()
    title       = input("New title        : ").strip() or None
    date        = input("New date (YYYY-MM-DD): ").strip() or None
    start_time  = input("New start (HH:MM): ").strip() or None
    end_time    = input("New end   (HH:MM): ").strip() or None
    description = input("New description  : ").strip() or None
    location    = input("New location     : ").strip() or None

    result = edit_event(
        service,
        event_id=event_id,
        title=title,
        date=date,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
    )

    print(f"\n✅ Updated: {result['title']}")
    print(f"   📅 {result['start']} → {result['end']}")
    print(f"   🔗 {result['link']}")


if __name__ == "__main__":
    main()
