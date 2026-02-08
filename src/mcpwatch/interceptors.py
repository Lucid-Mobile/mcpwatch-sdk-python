"""Interceptors for MCP server methods."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Coroutine

from mcpwatch.batcher import EventBatcher
from mcpwatch.types import EventType, McpWatchEvent
from mcpwatch.utils import generate_id, generate_span_id, now_iso, duration_ms


def wrap_tool_handler(
    handler: Callable[..., Coroutine[Any, Any, Any]],
    tool_name: str,
    batcher: EventBatcher,
    server_name: str,
    server_version: str,
    trace_id: str,
    sample_rate: float,
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Wrap a tool handler to capture events."""

    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        import random

        if random.random() > sample_rate:
            return await handler(*args, **kwargs)

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
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Wrap a resource handler to capture events."""

    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        import random

        if random.random() > sample_rate:
            return await handler(*args, **kwargs)

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
