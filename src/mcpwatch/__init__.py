"""MCPWatch SDK for MCP server observability."""

from mcpwatch.instrument import instrument
from mcpwatch.client import MCPWatchClient
from mcpwatch.transport import detect_transport_type

__all__ = ["instrument", "MCPWatchClient", "detect_transport_type"]
__version__ = "1.0.0"
