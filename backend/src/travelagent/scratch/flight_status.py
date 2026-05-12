from __future__ import annotations
import requests
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


def flight_status(AIRLINE_CODE,FLIGHT_NUMBER,DATE):

    # Get API key
    API_KEY=os.getenv("FLIGHT_API_KEY")
    # 2. Build the Endpoint URL
    # The structure is: https://flightapi.io
    url = f"https://api.flightapi.io/airline/{API_KEY}?num={FLIGHT_NUMBER}&name={AIRLINE_CODE}&date={DATE}"

    try:
        # 3. Make the Request
        response = requests.get(url)
    
        # Check for HTTP errors (e.g., 401 Unauthorized, 429 Too Many Requests)
        response.raise_for_status()
    
        # 4. Parse and Print the JSON Data
        data = response.json()
        print("Flight Data Received:")
        flights = data.get("flights")
        formatted_results = [f"**Flights Status Results ':**\n"]
        for index , flight in enumerate(flights,start=1):
            airlineCode= flight.get("airlineCode")
            flightNumber= flight.get("flightNumber")
            displayStatus= flight.get("displayStatus")
            departureTime = flight.get("departureTime")
            departureAirportCode = flight.get("departureAirportCode")
            arrivalAirportCode = flight.get("arrivalAirportCode")
            arrivalTime = flight.get("arrivalTime")

            formatted_results.append(
                f"{index}. **departure_airport:** {departureAirportCode}\n"
                f"   **departure_time:** {departureTime}\n"
                f"   **arrival_airport:** {arrivalAirportCode}\n"
                f"   **arrival_time:** {arrivalTime}\n" 
                f"   **airline:** {airlineCode}\n"
                f"   **flight_nubmer:** {flightNumber}\n"
                f"   **Status:** {displayStatus}\n"
                )
        print("\n".join(formatted_results))

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except Exception as err:
        print(f"An error occurred: {err}")

    return("\n".join(formatted_results))

print(flight_status("AA",6185,'20260507'))



#FLIGHT_NUMBER = '6185'      # e.g., 15
#AIRLINE_CODE = 'AA'       # e.g., AA for American Airlines
#DATE = '20260507'         # Format: YYYYMMDD