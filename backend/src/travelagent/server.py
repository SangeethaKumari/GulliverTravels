from fastmcp import FastMCP
from typing import Optional

# ── Init ──────────────────────────────────────────────
mcp = FastMCP(
    name="GulliverTravels MCP Server",
    version="0.2.0"
)

# ── Legacy Tool ───────────────────────────────────────
@mcp.tool()
def add_numbers(a: float, b: float) -> dict:
    """
    Adds two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        dict with result
    """
    return {
        "result": a + b,
        "operation": f"{a} + {b} = {a + b}"
    }


# ── Travel Companion MCP Tools ────────────────────────
from .companion import mcp_tools as companion_tools


@mcp.tool()
def get_flight_status(flight_number: str, date: Optional[str] = None) -> dict:
    """
    Get real-time flight status including delay, ETA, and trend.

    Args:
        flight_number: IATA flight code (e.g. "UA123")
        date: ISO date string (optional)

    Returns:
        dict with currentStatus, estimatedLanding, delayMinutes, etc.
    """
    return companion_tools.get_flight_status(flight_number, date)


@mcp.tool()
def get_weather(lat: float, lon: float, forecast_hours: int = 6) -> dict:
    """
    Get current weather conditions and trend at a location.

    Args:
        lat: Latitude
        lon: Longitude
        forecast_hours: Hours of forecast to include (1-24)

    Returns:
        dict with current conditions and trend
    """
    return companion_tools.get_weather(lat, lon, forecast_hours)


@mcp.tool()
def estimate_route(origin: str, destination: str, depart_time: Optional[str] = None) -> dict:
    """
    Estimate drive time under current traffic conditions.

    Args:
        origin: Origin location name or coordinates
        destination: Destination location name or coordinates
        depart_time: ISO timestamp for departure (optional, defaults to now)

    Returns:
        dict with durationSeconds, congestionLevel, distanceKm
    """
    return companion_tools.estimate_route(origin, destination, depart_time)


@mcp.tool()
def get_calendar_events(user_id: str) -> list:
    """
    Get upcoming calendar events for a user.

    Args:
        user_id: User identifier

    Returns:
        list of calendar event dicts
    """
    return companion_tools.get_calendar_events(user_id)


@mcp.tool()
def book_ride(pickup_lat: float, pickup_lon: float,
              dropoff_lat: float, dropoff_lon: float,
              request_time: str, service: str = "uber") -> dict:
    """
    Pre-book a rideshare pickup.

    Args:
        pickup_lat: Pickup latitude
        pickup_lon: Pickup longitude
        dropoff_lat: Dropoff latitude
        dropoff_lon: Dropoff longitude
        request_time: ISO timestamp for desired pickup
        service: "uber" or "lyft"

    Returns:
        dict with rideId, driverName, etaMinutes, estimatedFareUSD
    """
    from datetime import datetime
    req_dt = datetime.fromisoformat(request_time)
    return companion_tools.book_ride(
        pickup=(pickup_lat, pickup_lon),
        dropoff=(dropoff_lat, dropoff_lon),
        request_time=req_dt,
        service=service,
    )


@mcp.tool()
def cancel_ride(ride_id: str) -> dict:
    """
    Cancel a previously booked ride.

    Args:
        ride_id: The ride identifier returned from book_ride

    Returns:
        dict with cancellation status
    """
    return companion_tools.cancel_ride(ride_id)


# ── Entry Point ───────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8001)

