from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from ..tools.calendar_tool import book_meeting
import os

calendar_agent = LlmAgent(
    model=LiteLlm(
        model="gemini/gemini-2.5-flash",
        api_key=os.getenv("GOOGLE_API_KEY")
    ),
    name="calendar_agent",
    description="A specialist for scheduling meetings and managing calendar events.",
    instruction="""
    SYSTEM: YOU ARE A SILENT COORDINATOR.
    1. Extract the landing time from history.
    2. Book a meeting for 2 hours later.
    
    CRITICAL: 
    - DO NOT explain your reasoning.
    - DO NOT output any internal monologue.
    - YOUR FINAL RESPONSE MUST BE EXACTLY: 'Flight Confirmed: [Flight Info] | Meeting Confirmed: [Meeting Time]'
    """,
    tools=[book_meeting]
)