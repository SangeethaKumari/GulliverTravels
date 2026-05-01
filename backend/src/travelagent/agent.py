import os
from google.adk.agents.llm_agent import Agent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from .subagents.calendar_agent import calendar_agent
from .subagents.flight_search_agent import flight_search_agent

# Use SequentialAgent to ensure step-by-step execution
root_agent = SequentialAgent(
    name='root_agent',
    sub_agents=[flight_search_agent, calendar_agent],
    description='A travel assistant that first finds a flight and then schedules a follow-up meeting.'
)

if __name__ == "__main__":
    # This will trigger the logic and show you the handoff
    user_query = "search for a flight from SFO to LA and book a meeting 2 hours after landing"
    
    runner = InMemoryRunner(agent=root_agent)
    new_message = types.Content(role="user", parts=[types.Part(text=user_query)])
    
    print(f"Running query: {user_query}")
    events = runner.run(new_message=new_message)
    
    for event in events:
        if hasattr(event, 'content') and event.content:
            for part in event.content.parts:
                if part.text:
                    print(part.text, end="", flush=True)
    print()