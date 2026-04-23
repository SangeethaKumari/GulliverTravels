from fastmcp import FastMCP

# ── Init ──────────────────────────────────────────────
mcp = FastMCP(
    name="GulliverTravels MCP Server",
    version="0.1.0"
)

# ── Sample Tool ───────────────────────────────────────
@mcp.tool()
def add_numbers(a: float, b: float) -> dict:
    """
    Adds two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        dict with result
    """
    return {
        "result": a + b,
        "operation": f"{a} + {b} = {a + b}"
    }


# ── Entry Point ───────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8001)

