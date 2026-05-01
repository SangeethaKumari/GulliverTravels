from google.adk.agents.sequential_agent import SequentialAgent
import inspect

# Print the __init__ signature
print(f"SequentialAgent init signature: {inspect.signature(SequentialAgent.__init__)}")

# Try sub_agents
try:
    s = SequentialAgent(name="test", sub_agents=[])
    print("SequentialAgent supports sub_agents")
except Exception as e:
    print(f"SequentialAgent sub_agents error: {e}")

# Try agents
try:
    s = SequentialAgent(name="test", agents=[])
    print("SequentialAgent supports agents")
except Exception as e:
    print(f"SequentialAgent agents error: {e}")
