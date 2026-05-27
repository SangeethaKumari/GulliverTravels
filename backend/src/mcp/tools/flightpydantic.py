import datetime
from pydantic import BaseModel
from datetime import date

####################################################
#                 flight_status_realtime           #
####################################################

class FlightStatusRealtime(BaseModel):
    Departure_Airport:str
    Departure_Time:date
    Arrival_Airport:str
    Arrival_Time:date
    airline_code:str
    flight_nubmer:str
    Status:str





####################################################
#                 flight_status_realtime           #
####################################################


####################################################
#                 flight_status_realtime           #
####################################################