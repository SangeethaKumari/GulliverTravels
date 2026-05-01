import os
from google.adk.agents.llm_agent import Agent

try:
    agent = Agent(name="test")
    print("Agent works without model")
except Exception as e:
    print(f"Agent error: {e}")
