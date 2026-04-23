import os
from google.adk.agents.llm_agent import Agent
from google.adk.models.lite_llm import LiteLlm

root_agent = Agent(
    model=LiteLlm(
        model="openai/openai/gpt-oss-20b",
        api_base=os.getenv("LITELLM_API_BASE", "http://10.0.10.51:8124/v1"),
        api_key=os.getenv("LITELLM_API_KEY", "sv-openai-api-key")
    ),
    name='root_agent',
    description='A helpful assistant for user questions.',
    instruction='Answer user questions to the best of your knowledge',
)
