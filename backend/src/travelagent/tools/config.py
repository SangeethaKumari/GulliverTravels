"""
config.py — Shared configuration and Google Calendar authentication.
All other modules import get_service() and constants from here.
"""

import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import google.generativeai as genai

# ── Constants ─────────────────────────────────────────────────────────────────
SCOPES        = ["https://www.googleapis.com/auth/calendar"]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
TIMEZONE      = os.getenv("CALENDAR_TIMEZONE", "America/Los_Angeles")
TOKEN_FILE    = "token.pickle"
CREDS_FILE    = "credentials.json"

# Configure Gemini once at import time
genai.configure(api_key=GEMINI_API_KEY)


# ── Auth ──────────────────────────────────────────────────────────────────────
def get_service():
    """
    Authenticate with Google Calendar and return a service object.
    Saves/reloads token from token.pickle so the browser flow only
    runs once.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as fh:
            creds = pickle.load(fh)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_FILE):
                raise FileNotFoundError(
                    f"{CREDS_FILE} not found. "
                    "Download OAuth credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as fh:
            pickle.dump(creds, fh)

    return build("calendar", "v3", credentials=creds)
