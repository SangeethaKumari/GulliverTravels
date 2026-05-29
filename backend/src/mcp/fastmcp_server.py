"""
This builds an mcp server using the fastmcp v2 library.

To call the tools from a client once the server is running, send HTTP requests to the server's
endpoint. For example, to use the 'addition' tool, send a POST request to 'http://127.0.0.1:9000/mcp/addition'
with a JSON payload containing the parameters 'a' and 'b'. Similarly, to use the 'serper_search' tool,
send a POST request to 'http://127.0.0.1:9000/mcp/serper_search' with a JSON payload containing the parameter 'query'.

For more details, refer to the FastMCP documentation: https://gofastmcp.com/clients/client

Apart from the addition and serper_search tools that are defined within this file, this server also exposes the following tools:
- addition: Add two numbers together. (from add_tool.py)
- serper_search: Fetch news articles from Serper API for a given query/topic. (from serper_tool.py)
"""

from datetime import date, datetime
from fastmcp import FastMCP
from backend.src.mcp.tools.tools import add, fetch_fights_info, fetch_serper_news, flight_status_realtime
from backend.src.mcp.tools.config import get_service
from backend.src.mcp.tools.delete_calendar import get_event_details
mcp = FastMCP(name="Gulliver_Test Agent")


"""################################## MCP module for tGuliver Travels agent ################################## """

#####################################################################
#   Author ----------------------------NJ                           #
#####################################################################
@mcp.tool()
def addition(a: int, b: int) -> int:
    """
    Add two numbers together.
    """
    return add(a, b)

@mcp.tool
def serper_search(query: str) -> str:
    """
    Fetch recent news articles using the Serper API for a given query.
    """
    return fetch_serper_news(query)

@mcp.tool
def flight_search(departure_airport: str,arrival_airport:str,outbound_date,return_date) -> str:
    """
    Fetch Flight information using the Serper API and google flights.
    """
    return fetch_fights_info(departure_airport,arrival_airport,outbound_date,return_date)

@mcp.tool
def flight_status(airline_code:str,flight_number:str,input_date:datetime):
    """
    Fetch Flight Status real time 
    """
    return flight_status_realtime(airline_code,flight_number,input_date)

#####################################################################
#   Author ----------------------------Vani                          #
#####################################################################





#####################################################################
#   Author ----------------------------SR                          #
#####################################################################





#####################################################################
#   Author ----------------MOCK------------Sangeetha                          #
#####################################################################
def get_weather(lat: float, lon: float) -> dict:
    """Mock tool for destination weather tracking."""
    print(f"[Tool Call] Fetching weather for coordinates: {lat}, {lon}")
    return {"condition": "Rainy", "visibility_miles": 3}

def estimate_route(origin: str, destination: str) -> dict:
    """Mock tool for live transit time mapping."""
    print(f"[Tool Call] Calculating route from {origin} to {destination}")
    return {"traffic_status": "Heavy", "baseline_drive_minutes": 45}

def get_calendar(meeting_id: str) -> dict:
    """Mock tool for checking meeting priority constraints with real Google Calendar API fallback."""
    print(f"[Tool Call] Accessing calendar registry for ID: {meeting_id}")
    try:
        service = get_service()
        details = get_event_details(service, meeting_id)
        is_flexible = "flexible" in details.get("title", "").lower()
        print(f"Meeting details: {details}")
      
        return {
            "meeting_title": details.get("title", "No Title"),
            "is_flexible": is_flexible,
            "start": details.get("start"),
            "end": details.get("end"),
            "attendees": details.get("attendees", [])
        }
    except Exception as e:
        print(f"Could not retrieve live event details for {meeting_id} ({e}). Returning mock fallback.")
        return {"meeting_title": "Executive Board Sync", "is_flexible": False}



if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=9000)