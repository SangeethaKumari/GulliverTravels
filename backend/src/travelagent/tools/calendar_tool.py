


def book_meeting(title: str, start_datetime: str, duration: str = "1h"):
    """
    Schedules a meeting in the calendar.
    Args:
        title: The name of the meeting.
        start_datetime: The ISO format timestamp (YYYYMMDDTHHMM).
        duration: How long the meeting lasts (e.g., '1h').
    """
    # This print statement confirms the "Main Agent -> Subagent -> Tool" flow
    print(f"\n[CALENDAR TOOL EXECUTION]")
    print(f"Successfully booked: '{title}'")
    print(f"Scheduled for: {start_datetime}")
    print(f"Duration: {duration}\n")

    # This dummy return string is what the Root Agent will see
    return f"CONFIRMED: Meeting '{title}' scheduled for {start_datetime}."