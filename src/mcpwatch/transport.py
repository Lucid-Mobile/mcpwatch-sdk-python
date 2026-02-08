"""Transport type detection for MCP servers."""

from __future__ import annotations

from typing import Any

# Known transport class-name suffixes used across MCP SDK implementations.
_TRANSPORT_MAP: dict[str, str] = {
    "StdioServerTransport": "stdio",
    "SSEServerTransport": "sse",
    "StreamableHTTPServerTransport": "streamable-http",
    "WebSocketServerTransport": "websocket",
}


def detect_transport_type(server: Any) -> str:
    """Detect the transport type from the server instance.

    Inspects well-known attributes (``transport``, ``_transport``,
    ``server_transport``) and falls back to checking the class hierarchy
    of the server object itself.  Returns a human-readable transport
    label such as ``"stdio"`` or ``"sse"``, or ``"unknown"`` when no
    match is found.
    """
    # 1. Check for a transport attribute on the server
    for attr in ("transport", "_transport", "server_transport"):
        transport_obj = getattr(server, attr, None)
        if transport_obj is not None:
            result = _match_class_name(transport_obj)
            if result != "unknown":
                return result

    # 2. Check if the server itself is a transport subclass
    result = _match_class_name(server)
    if result != "unknown":
        return result

    return "unknown"


def _match_class_name(obj: Any) -> str:
    """Walk the MRO of *obj* looking for a known transport class name."""
    for cls in type(obj).__mro__:
        cls_name = cls.__name__
        if cls_name in _TRANSPORT_MAP:
            return _TRANSPORT_MAP[cls_name]
    return "unknown"
