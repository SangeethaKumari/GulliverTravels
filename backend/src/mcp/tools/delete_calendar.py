"""
delete_calendar.py — Delete (cancel) a Google Calendar event.

Usage (standalone):
    python delete_calendar.py
"""
from backend.src.mcp.tools.config import get_service


# ── Core function ─────────────────────────────────────────────────────────────
def delete_event(service, event_id: str, notify_attendees: bool = True) -> dict:
    """
    Delete a calendar event by its ID.

    Args:
        service          : authenticated Google Calendar service
        event_id         : Google Calendar event ID
        notify_attendees : if True, sends cancellation emails to attendees

    Returns:
        dict with status and event_id
    """
    send_updates = "all" if notify_attendees else "none"

    service.events().delete(
        calendarId="primary",
        eventId=event_id,
        sendUpdates=send_updates,
    ).execute()

    return {
        "status":   "deleted",
        "event_id": event_id,
        "notified": notify_attendees,
    }


def get_event_details(service, event_id: str) -> dict:
    """
    Fetch a single event to preview before deletion.

    Returns:
        dict with title, start, end, attendees
    """
    e = service.events().get(calendarId="primary", eventId=event_id).execute()

    return {
        "title":     e.get("summary", "No title"),
        "start":     e["start"].get("dateTime", e["start"].get("date")),
        "end":       e["end"].get("dateTime",   e["end"].get("date")),
        "attendees": [a["email"] for a in e.get("attendees", [])],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    service = get_service()

    print("\n🗑️   Delete a Calendar Event")
    print("─" * 40)
    event_id = input("Event ID: ").strip()

    # Preview the event before deleting
    try:
        details = get_event_details(service, event_id)
        print(f"\nEvent found:")
        print(f"  Title : {details['title']}")
        print(f"  Start : {details['start']}")
        print(f"  End   : {details['end']}")
        if details["attendees"]:
            print(f"  Guests: {', '.join(details['attendees'])}")
    except Exception as e:
        print("Exception occurred: ", e)
        print("⚠️  Could not fetch event details. Double-check the ID.")
        return

    notify = input("\nNotify attendees with cancellation email? (yes/no): ").strip().lower()
    confirm = input(f"Delete '{details['title']}'? This cannot be undone. (yes/no): ").strip().lower()

    if confirm not in ("yes", "y"):
        print("Deletion cancelled.")
        return

    result = delete_event(service, event_id, notify_attendees=(notify in ("yes", "y")))
    print(f"\n✅ Event deleted (ID: {result['event_id']})")
    if result["notified"]:
        print("   📧 Cancellation emails sent to attendees.")


if __name__ == "__main__":
    main()