import os
from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm

llm = LiteLlm(model="openai/gpt-oss-20b", api_key="test")
try:
    agent = Agent(name="test", model=llm, tools=[lambda x: x])
    print("Agent supports tools")
except Exception as e:
    print(f"Agent error: {e}")

from google.adk.agents.sequential_agent import SequentialAgent
try:
    s_agent = SequentialAgent(name="test", tools=[lambda x: x])
    print("SequentialAgent supports tools")
except Exception as e:
    print(f"SequentialAgent error: {e}")
