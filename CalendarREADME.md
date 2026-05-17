# 🗓️ Agentic AI Calendar Assistant

A modular Python project that uses **Google Gemini AI** + **Google Calendar API** to book, edit, delete, and list calendar events via natural language or direct function calls.

---

## 📁 Project Structure

```
calendar_project/
├── config.py            # Shared auth & configuration (imported by all)
├── book_calendar.py     # Create new events with conflict detection
├── edit_calendar.py     # Update/reschedule existing events
├── delete_calendar.py   # Cancel/delete events with attendee notification
├── list_calendar.py     # List, filter, and search events
├── check_conflicts.py   # Detect scheduling overlaps before booking
├── calendar_agent.py    # Gemini AI agent — natural language interface
├── api.py               # FastAPI REST API exposing all modules
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

### Module responsibilities

| File | Responsibility |
|------|---------------|
| `config.py` | Google OAuth flow, token caching, Gemini setup, shared constants |
| `book_calendar.py` | Create events; runs conflict check first; CLI prompts |
| `edit_calendar.py` | Patch any field (title, date, time, location) on existing events |
| `delete_calendar.py` | Delete with event preview + confirmation; optional invite cancellation |
| `list_calendar.py` | List today / week / month / custom range / keyword search |
| `check_conflicts.py` | Overlap detection only — imported by `book_calendar` and the AI agent |
| `calendar_agent.py` | Gemini 1.5 Flash parses natural language, delegates to right module |
| `api.py` | FastAPI REST layer; one endpoint per module; `?force=true` conflict override |

### How modules connect

```
Your Request
    │
    ├─▶ calendar_agent.py   (natural language / AI chat)
    │       ├─▶ book_calendar.py  ──▶ check_conflicts.py
    │       ├─▶ edit_calendar.py
    │       ├─▶ delete_calendar.py
    │       └─▶ list_calendar.py
    │
    └─▶ api.py              (REST API)
            ├─▶ GET    /events       → list_calendar
            ├─▶ POST   /events       → book_calendar
            ├─▶ PUT    /events/{id}  → edit_calendar
            ├─▶ DELETE /events/{id}  → delete_calendar
            ├─▶ GET    /conflicts    → check_conflicts
            └─▶ POST   /chat         → calendar_agent

All modules import from:
    config.py  (get_service, TIMEZONE, GEMINI_API_KEY)
```

---
## ⚙️ Prerequisites

- Python 3.11+
- A Google Cloud project with **Google Calendar API** enabled
- OAuth 2.0 Desktop credentials downloaded as `credentials.json`
- A **Gemini API key** from [Google AI Studio](https://aistudio.google.com/)

---

## 🚀 Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get Google Calendar credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable **Google Calendar API** → APIs & Services → Library
4. Create credentials → **OAuth 2.0 Client ID** → Desktop app
5. Download and save as `credentials.json` in this folder
6. Add yourself as a test user → APIs & Services → OAuth consent screen → Test users

### 3. Set environment variables

```bash
export GEMINI_API_KEY=your_gemini_api_key_here
export CALENDAR_TIMEZONE=America/Los_Angeles     # optional, defaults to this
```

Or create a `.env` file:

```env
GEMINI_API_KEY=your_gemini_api_key_here
CALENDAR_TIMEZONE=America/New_York
```

### 4. Authenticate (first run only)

Running any module for the first time will open a browser window for Google OAuth. After you approve, a `token.pickle` file is saved — you won't need to log in again.

---

## 🧩 Running Each Module

Every module can be run standalone with an interactive CLI.

### Book a new event

```bash
python book_calendar.py
```

Prompts for title, date, time, description, attendees, location. Checks for conflicts before booking. If a conflict is found, asks for confirmation before proceeding.

### Edit an existing event

```bash
python edit_calendar.py
```

Enter the event ID and only the fields you want to change — everything else stays the same. Get event IDs by running `list_calendar.py` first.

### Delete an event

```bash
python delete_calendar.py
```

Shows a preview of the event before deletion. Asks whether to send cancellation emails to attendees. Requires typed confirmation before deleting.

### List events

```bash
python list_calendar.py
```

Menu options:
1. Today's events
2. This week's events
3. This month's events
4. Custom date range
5. Search by keyword

### Check for conflicts

```bash
python check_conflicts.py
```

Enter a date and time range. Returns any events that overlap with that slot.

### AI chat agent

```bash
python calendar_agent.py
```

Understands natural language. Examples:

```
You: Book a team standup tomorrow at 9am for 30 minutes
You: Schedule lunch with Priya on 2026-05-20 at 12:30
You: Show my events for today
You: Move the standup to 10am
You: Cancel the product review meeting
You: Search for 'review' meetings this week
```

If a conflict is detected, the agent warns you and waits. Reply `book anyway` to proceed.

---

## 🌐 REST API

### Start the server

```bash
uvicorn api:app --reload --port 8000
```

Interactive docs available at: `http://localhost:8000/docs`

### Endpoints

#### `GET /events` — List events

```bash
curl "http://localhost:8000/events?days_ahead=7"
curl "http://localhost:8000/events?date=2026-05-10&search=standup"
```

Query params: `date`, `days_ahead` (default 7), `max_results` (default 20), `search`

#### `POST /events` — Book an event

```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Team Standup",
    "date": "2026-05-10",
    "start_time": "09:00",
    "end_time": "09:30",
    "attendees": ["alice@company.com"],
    "location": "Zoom"
  }'
```

Returns `409 Conflict` if an overlap is found. Add `?force=true` to override:

```bash
curl -X POST "http://localhost:8000/events?force=true" ...
```

#### `PUT /events/{event_id}` — Edit an event

```bash
curl -X PUT http://localhost:8000/events/EVENT_ID \
  -H "Content-Type: application/json" \
  -d '{"start_time": "10:00", "end_time": "10:30"}'
```

Only include the fields you want to change.

#### `DELETE /events/{event_id}` — Delete an event

```bash
curl -X DELETE "http://localhost:8000/events/EVENT_ID?notify_attendees=true"
```

#### `GET /conflicts` — Check for conflicts

```bash
curl "http://localhost:8000/conflicts?date=2026-05-10&start_time=09:00&end_time=10:00"
```

Returns `has_conflict: true/false` and a list of overlapping events.

#### `POST /chat` — Natural language AI agent

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Book a standup tomorrow at 9am"}'
```

#### `GET /health` — Health check

```bash
curl http://localhost:8000/health
```

---

## ⚠️ Conflict Detection

Before any booking, `check_conflicts.py` fetches all events on that day and applies the standard interval overlap formula:

```
conflict = existing.start < new.end  AND  existing.end > new.start
```

All-day events are skipped. If conflicts are found:

- **CLI**: shows conflicting events, asks `Book anyway? (yes/no)`
- **AI agent**: warns and waits — reply `book anyway` to confirm
- **REST API**: returns HTTP `409` with conflict details; use `?force=true` to override

---

## 🔑 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Your Google Gemini API key |
| `CALENDAR_TIMEZONE` | `America/Los_Angeles` | Timezone for all events |

---

## 📦 Dependencies

```
google-auth
google-auth-oauthlib
google-auth-httplib2
google-api-python-client
google-generativeai
fastapi
uvicorn
pydantic
python-dotenv
```

Install all with:

```bash
pip install -r requirements.txt
```

---

## 🛠️ Troubleshooting

**`credentials.json not found`**
Download OAuth credentials from Google Cloud Console and place the file in the project folder.

**`403 access_denied` on Google login**
Add your Google account as a test user: Google Cloud Console → APIs & Services → OAuth consent screen → Test users → Add.

**`Error 409` from the API**
A conflicting event exists. Either pick a different time or add `?force=true` to the request.

**`token.pickle` auth errors**
Delete `token.pickle` and re-run — it will trigger a fresh browser login.

**Gemini returns invalid JSON**
The agent strips markdown code fences automatically. If it still fails, check that `GEMINI_API_KEY` is set correctly.
