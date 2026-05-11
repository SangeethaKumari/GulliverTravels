from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
import os
from ..tools.flight_tool import search_flights

flight_search_agent = LlmAgent(
    model=LiteLlm(
        model="gemini/gemini-2.5-flash",
        api_key=os.getenv("GOOGLE_API_KEY")
    ),
    name="flight_search_agent",
    description="A specialist tool for finding flight schedules, arrival times, and IATA airport codes.",
    instruction="""
    SYSTEM: YOU ARE A SILENT SEARCH ENGINE.
    1. If departure and arrival are known, call 'search_flights'.
    2. After the tool returns flight details, DO NOT OUTPUT ANY TEXT. Remain silent so the next agent can take over.
    3. ONLY output text if you are missing information and need to ask the user a question.
    
    CRITICAL: No reasoning, no confirmation, no monologue.
    """,
    tools=[search_flights]
)
