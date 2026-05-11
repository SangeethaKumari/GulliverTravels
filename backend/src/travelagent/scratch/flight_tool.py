
def search_flights(departure_id: str, arrival_id: str, outbound_date: str = "2026-05-01"):
    """
    Searches for available flights between two locations.
    Args:
        departure_id: 3-letter IATA code for departure (e.g., 'SFO').
        arrival_id: 3-letter IATA code for arrival (e.g., 'LAX').
        outbound_date: The date of travel in YYYY-MM-DD format.
    """
    # Verify the Root Agent's extraction logic
    print(f"\n[FLIGHT TOOL EXECUTION]")
    print(f"Searching: {departure_id} -> {arrival_id} on {outbound_date}")

    # Return a structured string that the Root Agent can parse
    # We include a clear 'Arrival' time so the next agent can do the math
    dummy_data = (
        f"Flight AA123 from {departure_id} to {arrival_id} is available. "
        f"Departure: 10:00 AM, Arrival: 12:00 PM."
    )
    
    print(f"Returning to Agent: {dummy_data}\n")
    return dummy_data