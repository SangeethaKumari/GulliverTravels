from __future__ import annotations
from tokenize import String
import requests
from datetime import datetime, date, time
from typing import List, final
from unittest import result
import serpapi
import os
import requests
import pandas as pd
from .flightpydantic import FlightStatusRealtime
from dotenv import load_dotenv
load_dotenv()

FLIGHT_STATUS_CALL_COUNT = 0
LAST_CALL_TIME = None



SERPER_API_KEY = os.getenv("SERPER_API_KEY")



"""################################## Tools module for tGuliver Travels agent ################################## """



#####################################################################
#   Author ----------------------------NJ                           #
#####################################################################
def add(a: int, b: int) -> int:
    """
        Add two numbers together (ADDITION TOOL)..

    Args:
        a (int) and b (int) .

    Returns:
        int: get the result of two numbers a and b.

    Example:
        >>> add( 2+ 5 )
        7
    """
    print(f"Adding {a} and {b}")
    return a + b

##################################################################################

def fetch_serper_news(query: str) -> str:
    

    """
    Search Google using Serper API and return formatted search results.

    Args:
        query (str):  Search the topic and find the news about that topic
       
    Returns:
        String : String values with list of values such as 
        f"{i}. **Title:** {title}\n"
                f"   **URL:** {link}\n"
                f"   **Summary:** {snippet}\n"
                f"   **Date:** {date}\n"
             

    Example:
        >>> fetch_serper_news("Trump")
        
    """

    print(f"Fetching news for query: {query}")
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    params = {"q": query, "num" : 8}
    
    response = requests.post(url, json=params, headers=headers)
    print(f"Fetching Response: {response}")
    
    if response.status_code == 200:
        results = response.json()
        organic_results = results.get("organic", [])
        
        if not organic_results:
            return f"No search results found for '{query}'."

        #print(f"organic_results: {organic_results}")
        
        # Format the results as a string
        formatted_results = [f"**Serper Search Results for '{query}':**\n"]
        #print(f"Formatted_results: {formatted_results}")
        
        for i, result in enumerate(organic_results[:8], 1):
            title = result.get("title", "No title")
            link = result.get("link", "No link")
            snippet = result.get("snippet", "No description")
            date = result.get("date", "")
            
            formatted_results.append(
                f"{i}. **Title:** {title}\n"
                f"   **URL:** {link}\n"
                f"   **Summary:** {snippet}\n"
                f"   **Date:** {date}\n"
            )
        #print(f"Formatted_results: {formatted_results}")
        return "\n".join(formatted_results)
    else:
        return f"Error: {response.status_code}, {response.text}"


##################################################################################


def fetch_fights_info(departure_airport: str,arrival_airport:str,outbound_date:date,return_date:date):
     
    """
    Search for the best flights for given paramerts

    Args:
        departure_airport(str):  from where are departing for example SFO
        arrival_airport(str):  from where are you want to arrive for example LAX
        outbound_date(date):   when do you want to start  
        return_date(date): when do you want to come back.

    Returns:
        String : String values with list of values such as 
        f"{index}. **departure_airport:** {departure_airport}\n"
                f"   **departure_time:** {ddate}\n"
                f"   **arrival_airport:** {arrival_airport}\n"
                f"   **arrival_time:** {arrival_time}\n"
                f"   **airline:** {air_line}\n"
                f"   **flight_nubmer:** {flight_nubmer}\n"
             

    Example:
        >>> fetch_fights_info("SFO","LAX","2026-05-08","2026-05-08")
        
    """
    
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

##################################################################################

def flight_status_realtime(airline_code:str,flight_number:str,input_date:date | str):

    
    print(f"Input date prodived is {input_date} and the type is {type(input_date)}")
    """
    get the flight status in real time

    Args:

        airline_code(str):  Airport code where you are arriving  for example SFO
        flight_number(Int): Flight number 1586
        input_date(date):  Data on when you are arriving . Make sure this is equal or greater then current date
      

    Returns:
        String : String values with list of values such as 
          f"{index}. **departure_airport:** {departureAirportCode}\n"
                f"   **departure_time:** {departureTime}\n"
                f"   **arrival_airport:** {arrivalAirportCode}\n"
                f"   **arrival_time:** {arrivalTime}\n" 
                f"   **airline:** {airlineCode}\n"
                f"   **flight_nubmer:** {flightNumber}\n"
                f"   **Status:** {displayStatus}\n"
             

    Example:
        >>> flight_status_realtime("AA",6185,'20260507')
        
    """
    if isinstance(input_date, date):
        input_date_str = input_date.strftime("%Y%m%d")
    else:
        input_date_str = input_date
    


    if datetime.strptime(input_date_str, "%Y%m%d").date() < date.today():
        raise ValueError(f"Date cannot be in the past: {input_date_str}")

    print("Inside the flight status real time function")

    # Get API key
    API_KEY=os.getenv("FLIGHT_API_KEY")
    # 2. Build the Endpoint URL
    # The structure is: https://flightapi.io
    url = f"https://api.flightapi.io/airline/{API_KEY}?num={flight_number}&name={airline_code}&date={input_date_str}"
    results = None
    formatted_results = []
    try:
        # 3. Make the Request
        response = requests.get(url)
    
        # Check for HTTP errors (e.g., 401 Unauthorized, 429 Too Many Requests)
        response.raise_for_status()
    
        # 4. Parse and Print the JSON Data
        data = response.json()
        #print(data)
        #print("Flight Data Received:")
        departure = data[0]
        arrival = data[1]
        status = data[3]
        formatted_results = [f"**Flights Status Results ':**\n"]
        departure_airport_code = departure.get("departure").get("airportCode")
        departure_time = departure.get("departure").get("departureDateTime")
        arrival_airport_code = arrival.get("arrival").get("airportCode")
        arrival_time = arrival.get("arrival").get("arrivalDateTime")
        airlineCode = airline_code
        flightNumber = flight_number
        displayStatus = status.get("status")

        results = FlightStatusRealtime(
            Departure_Airport=departure_airport_code,
            Departure_Time=departure_time,
            Arrival_Airport=arrival_airport_code,
            Arrival_Time=arrival_time,
            airline_code=airlineCode,
            flight_number=flightNumber,
            Status=displayStatus
        )

    except Exception as err:
        print(f"flight_status_realtime API call failed or limit reached: {err}. Returning mock fallback.")
        print(f"flight_status_realtime Input date is {input_date}")
        print(f"flight_status_realtime flight_number {flight_number}")
        if isinstance(input_date, date):
            d = input_date
            print("flight_status_realtime Input date is date")
        else:
            try:
                clean_date_str = input_date.replace("-", "").strip()
                d = datetime.strptime(clean_date_str, "%Y%m%d").date()
                print("flight_status_realtime Input date is datetime")
            except Exception:
                d = date.today()
        
        global FLIGHT_STATUS_CALL_COUNT, LAST_CALL_TIME
        now_time = datetime.now()
        if LAST_CALL_TIME is not None:
            elapsed = (now_time - LAST_CALL_TIME).total_seconds()
            # if elapsed > 120.0:
            #     FLIGHT_STATUS_CALL_COUNT = 0
            #     print(f"flight_status_realtime: Inactivity detected ({elapsed:.1f}s > 120s). Resetting mock call count to 0.")
        LAST_CALL_TIME = now_time
        
        FLIGHT_STATUS_CALL_COUNT += 1
        print(f"flight_status_realtime mock call count: {FLIGHT_STATUS_CALL_COUNT}")

        fn_str = flight_number
        print("Flight Number is " + fn_str)
        if "2486" in fn_str:
            if FLIGHT_STATUS_CALL_COUNT <= 3:
                status_val = "on_time"
                arr_dt = datetime(d.year, d.month, d.day, 17, 45, 0) # No delay
            elif FLIGHT_STATUS_CALL_COUNT == 4:
                status_val = "delayed"
                arr_dt = datetime(d.year, d.month, d.day, 18, 15, 0) # 30 min delay
            elif FLIGHT_STATUS_CALL_COUNT == 5:
                status_val = "delayed"
                arr_dt = datetime(d.year, d.month, d.day, 18, 45, 0) # 60 min delay
            else:
                status_val = "delayed"
                arr_dt = datetime(d.year, d.month, d.day, 19, 15, 0) # 90 min delay
        elif "456" in fn_str:
            status_val = "cancelled"
            arr_dt = datetime(d.year, d.month, d.day, 17, 45, 0)
        else:
            status_val = "on_time"
            arr_dt = datetime(d.year, d.month, d.day, 17, 45, 0)
            
        dep_dt = datetime(d.year, d.month, d.day, 12, 0, 0)
        
        results = FlightStatusRealtime(
            Departure_Airport="SFO",
            Departure_Time=dep_dt,
            Arrival_Airport="JFK",
            Arrival_Time=arr_dt,
            airline_code=airline_code,
            flight_number=flight_number,
            Status=status_val
        )

    return(results)



#####################################################################
#   Author ----------------------------Vani                         #
#####################################################################







#####################################################################
#   Author ----------------------------SR                         #
#####################################################################



#print(flight_status_realtime("AA","9305",date(2026,5,16)))
#print(fetch_fights_info("SFO","LAX","2026-05-17",Date(2026-05-20))