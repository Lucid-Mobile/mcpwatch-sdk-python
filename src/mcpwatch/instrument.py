"""Main instrument() function for wrapping MCP servers."""

from __future__ import annotations

import atexit
import functools
import logging
from typing import Any, TypeVar

from mcpwatch.batcher import EventBatcher
from mcpwatch.interceptors import wrap_tool_handler, wrap_resource_handler
from mcpwatch.transport import detect_transport_type
from mcpwatch.types import EventType, McpWatchEvent
from mcpwatch.utils import generate_id, generate_span_id, generate_trace_id, now_iso

logger = logging.getLogger("mcpwatch")

T = TypeVar("T")


def _extract_server_name(server: Any) -> str:
    """Try multiple attributes to find the server name."""
    for attr in ("name", "_name", "server_name", "_server_name"):
        val = getattr(server, attr, None)
        if val and isinstance(val, str):
            return val

    # Check for a server_info dict/object
    info = getattr(server, "server_info", None)
    if info is not None:
        if isinstance(info, dict):
            name = info.get("name")
            if name:
                return str(name)
        else:
            name = getattr(info, "name", None)
            if name:
                return str(name)

    return "unknown"


def _extract_server_version(server: Any) -> str:
    """Try multiple attributes to find the server version."""
    for attr in ("version", "_version", "server_version", "_server_version"):
        val = getattr(server, attr, None)
        if val and isinstance(val, str):
            return val

    info = getattr(server, "server_info", None)
    if info is not None:
        if isinstance(info, dict):
            version = info.get("version")
            if version:
                return str(version)
        else:
            version = getattr(info, "version", None)
            if version:
                return str(version)

    return "unknown"


def instrument(
    server: T,
    *,
    api_key: str,
    endpoint: str = "https://ingest.mcpwatch.dev",
    debug: bool = False,
    sample_rate: float = 1.0,
    max_batch_size: int = 50,
    flush_interval: float = 1.0,
) -> T:
    """
    Instrument an MCP server for observability.

    Wraps the server's tool and resource registration methods to automatically
    capture all interactions and send them to MCPWatch.

    Args:
        server: The MCP Server instance to instrument
        api_key: MCPWatch API key (e.g., "mw_live_...")
        endpoint: MCPWatch ingestion endpoint URL
        debug: Enable debug logging
        sample_rate: Sampling rate from 0.0 to 1.0
        max_batch_size: Maximum events per batch
        flush_interval: Seconds between batch flushes

    Returns:
        The same server instance, now instrumented
    """
    if not api_key:
        logger.warning("No API key provided, instrumentation disabled")
        return server

    batcher = EventBatcher(
        api_key=api_key,
        endpoint=endpoint,
        debug=debug,
        max_batch_size=max_batch_size,
        flush_interval=flush_interval,
    )

    # Extract server info using multi-attribute lookup
    server_name = _extract_server_name(server)
    server_version = _extract_server_version(server)
    transport_type = detect_transport_type(server)
    trace_id = generate_trace_id()

    # Shared mutable container for client info, captured on first handler call
    client_info: dict[str, Any] = {"name": "", "version": ""}

    # Store original methods
    original_tool = getattr(server, "tool", None)
    original_resource = getattr(server, "resource", None)

    if original_tool is not None:
        # Check if tool() is used as a decorator (Python MCP SDK pattern)
        def wrapped_tool(*args: Any, **kwargs: Any) -> Any:
            result = original_tool(*args, **kwargs)

            # If used as decorator: @server.tool()
            if callable(result) and not hasattr(result, "__wrapped_mcpwatch__"):
                def decorator(handler: Any) -> Any:
                    tool_name = args[0] if args else kwargs.get("name", handler.__name__)
                    wrapped_handler = wrap_tool_handler(
                        handler,
                        tool_name=str(tool_name),
                        batcher=batcher,
                        server_name=server_name,
                        server_version=server_version,
                        trace_id=trace_id,
                        sample_rate=sample_rate,
                        server=server,
                        client_info=client_info,
                    )
                    wrapped_handler.__wrapped_mcpwatch__ = True  # type: ignore
                    return result(wrapped_handler)

                return decorator

            return result

        setattr(server, "tool", wrapped_tool)

    if original_resource is not None:
        def wrapped_resource(*args: Any, **kwargs: Any) -> Any:
            result = original_resource(*args, **kwargs)

            if callable(result) and not hasattr(result, "__wrapped_mcpwatch__"):
                def decorator(handler: Any) -> Any:
                    resource_name = args[0] if args else kwargs.get("name", handler.__name__)
                    wrapped_handler = wrap_resource_handler(
                        handler,
                        resource_name=str(resource_name),
                        batcher=batcher,
                        server_name=server_name,
                        server_version=server_version,
                        trace_id=trace_id,
                        sample_rate=sample_rate,
                        server=server,
                        client_info=client_info,
                    )
                    wrapped_handler.__wrapped_mcpwatch__ = True  # type: ignore
                    return result(wrapped_handler)

                return decorator

            return result

        setattr(server, "resource", wrapped_resource)

    # ---- Lifecycle: wrap server.run() to emit initialize event ----
    original_run = getattr(server, "run", None)
    if original_run is not None and callable(original_run):

        @functools.wraps(original_run)
        async def wrapped_run(*args: Any, **kwargs: Any) -> Any:
            # Emit initialize event
            init_event = McpWatchEvent(
                event_id=generate_id(),
                trace_id=trace_id,
                span_id=generate_span_id(),
                event_type=EventType.INITIALIZE,
                event_name="server.initialize",
                mcp_method="initialize",
                started_at=now_iso(),
                ended_at=now_iso(),
                server_name=server_name,
                server_version=server_version,
                transport_type=transport_type,
            )
            batcher.add(init_event)

            return await original_run(*args, **kwargs)

        setattr(server, "run", wrapped_run)

    # ---- Lifecycle: atexit handler for close event ----
    def _emit_close_event() -> None:
        """Best-effort close event emitted when the process exits.

        At atexit time the async event loop is typically stopped or
        shutting down, so ``loop.create_task()`` would silently drop the
        flush.  Instead we always try ``asyncio.run()`` which creates a
        fresh temporary loop for the final flush.
        """
        close_event = McpWatchEvent(
            event_id=generate_id(),
            trace_id=trace_id,
            span_id=generate_span_id(),
            event_type=EventType.CLOSE,
            event_name="server.close",
            mcp_method="close",
            started_at=now_iso(),
            ended_at=now_iso(),
            server_name=server_name,
            server_version=server_version,
            transport_type=transport_type,
        )
        batcher.add(close_event)

        # Best-effort synchronous flush with a fresh event loop.
        # During interpreter shutdown some modules may already be torn
        # down, so we catch broadly and accept silent failure.
        import asyncio

        try:
            asyncio.run(batcher.flush())
        except Exception:
            pass

    atexit.register(_emit_close_event)

    # Start the batcher background loop.
    # The batcher.start() call creates an asyncio.Task, so it must be called
    # when an event loop is running. If no loop is running yet, we defer
    # starting to the first add() call by wrapping add().
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        # If we got here, a loop is running -- safe to start now
        batcher.start()
    except RuntimeError:
        # No running event loop yet. Wrap batcher.add to lazily start
        # the flush loop on the first event.
        import asyncio

        _original_add = batcher.add

        def _lazy_start_add(event: Any) -> None:
            if not batcher._running:
                try:
                    asyncio.get_running_loop()
                    batcher.start()
                except RuntimeError:
                    pass
            _original_add(event)

        batcher.add = _lazy_start_add  # type: ignore

    if debug:
        logger.info(f"Instrumented server '{server_name}' v{server_version} (transport={transport_type})")

    return server
