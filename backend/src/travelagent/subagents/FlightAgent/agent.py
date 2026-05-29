# =============================================================================
# IMPORTS
# =============================================================================

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from dotenv import load_dotenv
load_dotenv()
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams, McpToolset
#from phoenix.otel import register
#from openinference.instrumentation.google_adk import GoogleADKInstrumentor

#tracer_provider = register(

#    project_name="adk-agent-01",
#)
#GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
# =============================================================================
# CONFIGURATION
# =============================================================================

MODEL = "gpt-4o-mini"  # Primary model for news collection agents
OLLAMA_MODEL = "ollama_chat/qwen3:8b"  # Alternative model for validation tasks

# =============================================================================
# MCP SERVER
# =============================================================================

# --- Define MCP Tool Getter ---
def get_mcp_tool():
    """
    Safely instantiate MCPToolset to avoid Pydantic schema serialization issues.
    
    This connects the agent to an external MCP server via Streamable HTTP.
    The MCP server can expose tools such as web_search, file_read, or custom logic.
    """
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url="http://127.0.0.1:9000/mcp"   # Your FastMCP or MCP server endpoint
        )
    )
    
mcp_tool = get_mcp_tool()

# =============================================================================
# CONTENT ANALYSIS AGENT
# =============================================================================

# --- Define the LLM Agent ---
generic_agent = LlmAgent(
    name="Generic",
    model=LiteLlm(model="gemini/gemini-2.5-flash"),
    instruction="Respond to the user's request. Use the appropriate tools if necessary.",
    tools=[mcp_tool]
)


root_agent = generic_agent