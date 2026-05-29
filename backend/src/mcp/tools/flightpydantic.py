import datetime
from pydantic import BaseModel
from datetime import datetime

####################################################
#                 flight_status_realtime           #
####################################################

class FlightStatusRealtime(BaseModel):
    Departure_Airport:str
    Departure_Time:datetime
    Arrival_Airport:str
    Arrival_Time:datetime
    airline_code:str
    flight_number:str
    Status:str





####################################################
#                 flight_status_realtime           #
####################################################


####################################################
#                 flight_status_realtime           #
####################################################