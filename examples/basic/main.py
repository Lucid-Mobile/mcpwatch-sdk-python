"""Basic example of using MCPWatch with an MCP server."""

import os
from mcp.server import Server
from mcpwatch import instrument

app = instrument(
    Server("example-weather-server"),
    api_key=os.environ.get("MCPWATCH_API_KEY", ""),
    endpoint=os.environ.get("MCPWATCH_ENDPOINT", "https://ingest.mcpwatch.dev"),
    debug=True,
)


@app.tool("get_weather")
async def get_weather(city: str) -> str:
    return f"The weather in {city} is 72\u00b0F and sunny."


if __name__ == "__main__":
    print("Weather server with MCPWatch instrumentation ready")
