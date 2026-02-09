"""Interceptors for MCP server methods."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Coroutine

from mcpwatch.batcher import EventBatcher
from mcpwatch.types import EventType, McpWatchEvent
from mcpwatch.utils import generate_id, generate_span_id, now_iso, duration_ms


def _try_capture_client_info(server: Any, client_info: dict[str, Any]) -> None:
    """Best-effort extraction of client name/version from the MCP server's request context."""
    if client_info.get("_captured"):
        return
    try:
        ctx = getattr(server, "request_context", None)
        if ctx is None:
            return
        session = getattr(ctx, "session", None)
        if session is None:
            return
        # The Python MCP SDK stores client params from the initialize handshake
        client_params = getattr(session, "_client_params", None) or getattr(
            session, "client_params", None
        )
        if client_params is not None:
            info = getattr(client_params, "clientInfo", None) or getattr(
                client_params, "client_info", None
            )
            if info is not None:
                client_info["name"] = getattr(info, "name", "") or ""
                client_info["version"] = getattr(info, "version", "") or ""
        client_info["_captured"] = True
    except Exception:
        client_info["_captured"] = True


def wrap_tool_handler(
    handler: Callable[..., Coroutine[Any, Any, Any]],
    tool_name: str,
    batcher: EventBatcher,
    server_name: str,
    server_version: str,
    trace_id: str,
    sample_rate: float,
    server: Any = None,
    client_info: dict[str, Any] | None = None,
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Wrap a tool handler to capture events."""

    _client_info = client_info or {}

    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        import random

        if random.random() > sample_rate:
            return await handler(*args, **kwargs)

        if server is not None:
            _try_capture_client_info(server, _client_info)

        start_time = time.perf_counter()
        event = McpWatchEvent(
            event_id=generate_id(),
            trace_id=trace_id,
            span_id=generate_span_id(),
            event_type=EventType.TOOL_CALL,
            event_name=tool_name,
            mcp_method="tools/call",
            started_at=now_iso(),
            server_name=server_name,
            server_version=server_version,
            client_name=_client_info.get("name", ""),
            client_version=_client_info.get("version", ""),
            request_params=_safe_dict(args[0] if args else kwargs),
        )

        try:
            result = await handler(*args, **kwargs)
            event.ended_at = now_iso()
            event.duration_ms = duration_ms(start_time)
            event.response_content = _safe_dict(result)

            # Check for MCP error response
            if hasattr(result, "isError") and result.isError:
                event.is_error = True
                event.error_message = str(result)

            batcher.add(event)
            return result
        except Exception as e:
            event.ended_at = now_iso()
            event.duration_ms = duration_ms(start_time)
            event.is_error = True
            event.error_message = str(e)
            batcher.add(event)
            raise

    return wrapper


def wrap_resource_handler(
    handler: Callable[..., Coroutine[Any, Any, Any]],
    resource_name: str,
    batcher: EventBatcher,
    server_name: str,
    server_version: str,
    trace_id: str,
    sample_rate: float,
    server: Any = None,
    client_info: dict[str, Any] | None = None,
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Wrap a resource handler to capture events."""

    _client_info = client_info or {}

    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        import random

        if random.random() > sample_rate:
            return await handler(*args, **kwargs)

        if server is not None:
            _try_capture_client_info(server, _client_info)

        start_time = time.perf_counter()
        event = McpWatchEvent(
            event_id=generate_id(),
            trace_id=trace_id,
            span_id=generate_span_id(),
            event_type=EventType.RESOURCE_READ,
            event_name=resource_name,
            mcp_method="resources/read",
            started_at=now_iso(),
            server_name=server_name,
            server_version=server_version,
            client_name=_client_info.get("name", ""),
            client_version=_client_info.get("version", ""),
        )

        try:
            result = await handler(*args, **kwargs)
            event.ended_at = now_iso()
            event.duration_ms = duration_ms(start_time)
            event.response_content = _safe_dict(result)
            batcher.add(event)
            return result
        except Exception as e:
            event.ended_at = now_iso()
            event.duration_ms = duration_ms(start_time)
            event.is_error = True
            event.error_message = str(e)
            batcher.add(event)
            raise

    return wrapper


def _safe_dict(obj: Any) -> dict[str, Any]:
    """Safely convert an object to a dict for serialization."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return {"value": str(obj)}
