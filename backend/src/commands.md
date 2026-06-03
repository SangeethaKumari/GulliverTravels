#   List Calendar Events
(gullivertravels) (base) sangeetha@Sangeethas-MacBook-Pro GulliverTravels % PYTHONPATH=. uv run python -c "
from backend.src.mcp.tools.config import get_service
from datetime import datetime, timezone
service = get_service()
now = datetime.now(timezone.utc).isoformat()
events = service.events().list(
    calendarId='primary',
    maxResults=10,
    singleEvents=True,
    orderBy='startTime',
    timeMin=now
).execute()
for e in events.get('items', []):
    print(e['id'], '|', e.get('summary','No title'), '|', e['start'].get('dateTime', e['start'].get('date')))
"

# Get DB details from terminal
sqlite3 orchestrator_state.db
.headers on
.mode columns
SELECT * from sessions;

rm orchestrator_state.db


# run the ambient orchestrator
(gullivertravels) (base) sangeetha@Sangeethas-MacBook-Pro src % PYTHONPATH=. uv run python -m backend.src.travelagent.AmbientOrchestration

# run the mcpserver 
(gullivertravels) (base) sangeetha@Sangeethas-MacBook-Pro GulliverTravels % uv run python -m backend.src.mcp.fastmcp_server

# To run the unit tests
(gullivertravels) (base) sangeetha@Sangeethas-MacBook-Pro GulliverTravels % PYTHONPATH=. uv run pytest backend/src/tests/test_call_time_agent.py

# Alternatively, run the test script directly
(gullivertravels) (base) sangeetha@Sangeethas-MacBook-Pro GulliverTravels % PYTHONPATH=. uv run python backend/src/tests/test_call_time_agent.py

