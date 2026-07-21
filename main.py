import os
from fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("My Custom Data Server")


# EXAMPLE TOOL: Replace or add your custom logic here!
@mcp.tool()
def search_my_data(query: str) -> str:
    """Search my custom private database/records."""
    # Insert your custom logic or database call here
    return f"Results for '{query}': Here is the custom data you requested!"


if __name__ == "__main__":
    # Render assigns a dynamic PORT via environment variable
    port = int(os.environ.get("PORT", 10000))
    # Run the server using HTTP transport
    mcp.run(transport="http", host="0.0.0.0", port=port)
