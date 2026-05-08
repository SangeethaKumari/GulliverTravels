from __future__ import annotations
from datetime import datetime, date, time
from typing import List, final
from unittest import result
from pydantic import BaseModel, TypeAdapter
import serpapi
import os
import requests
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

def fetch_fights_info(departure_airport: str,arrival_airport:str,outbound_date:str,return_date:str):
    """Search Serper API for Flight info using google search and return formatted with Pydantic search results."""
    client = serpapi.Client(api_key=os.getenv("API_KEY"))
    results = client.search({
        "engine": "google_flights",
        "departure_id":departure_airport,     #"SFO"
        "arrival_id": arrival_airport ,       #"LAX"
        "outbound_date": outbound_date,
        "return_date": return_date,
        "currency": "USD",
        "hl": "en"})
    flights = results["best_flights"]
    final_results = []
    for item in flights:
        final_results += item["flights"]

    formatted_results = [f"**Flights Search Results ':**\n"]

    for index , item in enumerate(final_results,start=1):
        departure_airport = item.get("departure_airport").get("id") 
        departure_time = item.get("departure_airport").get("time") # De time
        arrival_airport = item.get("arrival_airport").get("id")
        arrival_time = item.get("arrival_airport").get("time")
        air_line = item.get("airline")
        flight_nubmer = item.get("flight_number")
        ddate = pd.to_datetime( departure_time)
        adate = pd.to_datetime(arrival_time)

        formatted_results.append(
                f"{index}. **departure_airport:** {departure_airport}\n"
                f"   **departure_time:** {ddate}\n"
                f"   **arrival_airport:** {arrival_airport}\n"
                f"   **arrival_time:** {arrival_time}\n"
                f"   **airline:** {air_line}\n"
                f"   **flight_nubmer:** {flight_nubmer}\n"
                )
    return "\n".join(formatted_results)


    




print(fetch_fights_info("SFO","LAX","2026-05-08","2026-05-08"))
#print(os.getenv("API_KEY"))