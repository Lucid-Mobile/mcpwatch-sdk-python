"""MCPWatch SDK for MCP server observability."""

from mcpwatch.instrument import instrument
from mcpwatch.client import MCPWatchClient

__all__ = ["instrument", "MCPWatchClient"]
__version__ = "0.1.0"
