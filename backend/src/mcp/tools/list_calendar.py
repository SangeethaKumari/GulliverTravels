"""
list_calendar.py — List Google Calendar events for a given time range.
"""

import datetime
from zoneinfo import ZoneInfo

try:
    from backend.src.mcp.tools.config import TIMEZONE
except ImportError:
    TIMEZONE = "America/Los_Angeles"


def list_events(
    service,
    date: str | None = None,
    days_ahead: int = 7,
    search: str | None = None,
    max_results: int = 50,
) -> list[dict]:
    """
    List events from the primary Google Calendar.

    Args:
        service    : authenticated Google Calendar service instance
        date       : starting date string (YYYY-MM-DD), defaults to now
        days_ahead : number of days ahead to search
        search     : keyword to filter events
        max_results: max number of events to fetch
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.datetime.now(tz)

    if date:
        try:
            start_dt = datetime.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError:
            start_dt = now
    else:
        start_dt = now

    end_dt = start_dt + datetime.timedelta(days=days_ahead)

    time_min = start_dt.isoformat()
    time_max = end_dt.isoformat()

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=max_results,
            q=search,
        )
        .execute()
    )

    items = events_result.get("items", [])
    events = []
    for item in items:
        start = item["start"].get("dateTime", item["start"].get("date"))
        end = item["end"].get("dateTime", item["end"].get("date"))
        events.append({
            "event_id": item["id"],
            "title":    item.get("summary", "No title"),
            "start":    start,
            "end":      end,
        })

    return events
