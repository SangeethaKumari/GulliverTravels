"""
book_calendar.py — Create new Google Calendar events.

Includes conflict detection before booking. If a time clash is found,
the user is warned and can confirm with 'book anyway'.

Usage (standalone):
    python book_calendar.py
"""

import datetime
from zoneinfo import ZoneInfo
from config import get_service, TIMEZONE
from check_conflicts import check_conflicts


# ── Core function ─────────────────────────────────────────────────────────────
def book_event(
    service,
    title: str,
    date: str,
    start_time: str,
    end_time: str,
    description: str = "",
    attendees: list[str] = [],
    location: str = "",
    force: bool = False,
) -> dict:
    """
    Book a new calendar event after checking for conflicts.

    Args:
        service     : authenticated Google Calendar service
        title       : event summary / title
        date        : YYYY-MM-DD
        start_time  : HH:MM  (24-hour)
        end_time    : HH:MM  (24-hour)
        description : optional event body text
        attendees   : list of email strings
        location    : optional location string
        force       : if True, skip conflict check and book directly

    Returns:
        dict with status, event_id, title, start, end, link
        OR dict with status='conflict' and conflicts list
    """
    tz = ZoneInfo(TIMEZONE)

    # ── Conflict check ────────────────────────────────────────────────────────
    if not force:
        conflicts = check_conflicts(service, date, start_time, end_time)
        if conflicts:
            return {
                "status": "conflict",
                "message": (
                    f"{len(conflicts)} existing event(s) overlap "
                    f"{start_time}–{end_time} on {date}."
                ),
                "conflicts": conflicts,
                "hint": "Call book_event(..., force=True) to override.",
            }

    # ── Build & insert event ──────────────────────────────────────────────────
    start_dt = datetime.datetime.strptime(
        f"{date} {start_time}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=tz)
    end_dt = datetime.datetime.strptime(
        f"{date} {end_time}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=tz)

    body = {
        "summary": title,
        "description": description,
        "location": location,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": TIMEZONE},
        "attendees": [{"email": e} for e in attendees],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email",  "minutes": 24 * 60},
                {"method": "popup",  "minutes": 30},
            ],
        },
    }

    event = (
        service.events()
        .insert(calendarId="primary", body=body, sendUpdates="all")
        .execute()
    )

    return {
        "status":   "booked",
        "event_id": event["id"],
        "title":    title,
        "start":    start_dt.strftime("%Y-%m-%d %H:%M"),
        "end":      end_dt.strftime("%Y-%m-%d %H:%M"),
        "link":     event.get("htmlLink", ""),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    service = get_service()

    print("\n📅  Book a New Calendar Event")
    print("─" * 40)
    title       = input("Title        : ").strip()
    date        = input("Date (YYYY-MM-DD): ").strip()
    start_time  = input("Start (HH:MM): ").strip()
    end_time    = input("End   (HH:MM): ").strip()
    description = input("Description  : ").strip()
    attendees   = input("Attendees (comma-separated emails, or blank): ").strip()
    location    = input("Location     : ").strip()

    attendee_list = [a.strip() for a in attendees.split(",") if a.strip()]

    result = book_event(
        service,
        title=title,
        date=date,
        start_time=start_time,
        end_time=end_time,
        description=description,
        attendees=attendee_list,
        location=location,
    )

    if result["status"] == "conflict":
        print(f"\n⚠️  {result['message']}")
        for c in result["conflicts"]:
            print(f"   • {c['title']}  ({c['start']} – {c['end']})")
        confirm = input("\nBook anyway? (yes/no): ").strip().lower()
        if confirm in ("yes", "y"):
            result = book_event(
                service, title, date, start_time, end_time,
                description, attendee_list, location, force=True,
            )
        else:
            print("Booking cancelled.")
            return

    print(f"\n✅ Booked: {result['title']}")
    print(f"   📅 {result['start']} → {result['end']}")
    print(f"   🔗 {result['link']}")


if __name__ == "__main__":
    main()
