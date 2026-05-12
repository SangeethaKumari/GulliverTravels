"""
This builds an mcp server using the fastmcp v2 library.

To call the tools from a client once the server is running, send HTTP requests to the server's
endpoint. For example, to use the 'addition' tool, send a POST request to 'http://127.0.0.1:9000/mcp/addition'
with a JSON payload containing the parameters 'a' and 'b'. Similarly, to use the 'serper_search' tool,
send a POST request to 'http://127.0.0.1:9000/mcp/serper_search' with a JSON payload containing the parameter 'query'.

For more details, refer to the FastMCP documentation: https://gofastmcp.com/clients/client

Apart from the addition and serper_search tools that are defined within this file, this server also exposes the following tools:
- addition: Add two numbers together. (from add_tool.py)
- serper_search: Fetch news articles from Serper API for a given query/topic. (from serper_tool.py)
"""

from fastmcp import FastMCP
from tools.tools import add,fetch_fights_info,fetch_serper_news,flight_status_realtime
mcp = FastMCP(name="Gulliver_Test Agent")


"""################################## MCP module for tGuliver Travels agent ################################## """

#####################################################################
#   Author ----------------------------NJ                           #
#####################################################################
@mcp.tool()
def addition(a: int, b: int) -> int:
    """
    Add two numbers together.
    """
    return add(a, b)

@mcp.tool
def serper_search(query: str) -> str:
    """
    Fetch recent news articles using the Serper API for a given query.
    """
    return fetch_serper_news(query)

@mcp.tool
def flight_search() -> str:
    """
    Fetch Flight information using the Serper API and google flights.
    """
    return fetch_fights_info()

@mcp.tool
def flight_status() -> str:
    """
    Fetch Flight Status real time 
    """
    return flight_status_realtime()

#####################################################################
#   Author ----------------------------Vani                          #
#####################################################################





#####################################################################
#   Author ----------------------------SR                          #
#####################################################################


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=9000)