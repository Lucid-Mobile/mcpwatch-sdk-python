"""Tests for the EventBatcher."""

import pytest
import pytest_asyncio
from mcpwatch.batcher import EventBatcher
from mcpwatch.types import EventType, McpWatchEvent


def create_test_event(**kwargs) -> McpWatchEvent:
    defaults = {
        "event_id": "test-id",
        "trace_id": "test-trace",
        "span_id": "test-span",
        "event_type": EventType.TOOL_CALL,
        "event_name": "test_tool",
        "started_at": "2026-02-08T00:00:00Z",
        "ended_at": "2026-02-08T00:00:00.100Z",
        "duration_ms": 100.0,
        "mcp_method": "tools/call",
        "server_name": "test-server",
        "server_version": "1.0.0",
    }
    defaults.update(kwargs)
    return McpWatchEvent(**defaults)


def test_batcher_creation():
    batcher = EventBatcher(
        api_key="mw_test_key",
        endpoint="http://localhost:0",
    )
    assert batcher is not None


def test_add_event():
    batcher = EventBatcher(
        api_key="mw_test_key",
        endpoint="http://localhost:0",
    )
    event = create_test_event()
    batcher.add(event)
    assert len(batcher._queue) == 1


@pytest.mark.asyncio
async def test_flush_empty():
    batcher = EventBatcher(
        api_key="mw_test_key",
        endpoint="http://localhost:0",
    )
    await batcher.flush()  # Should not raise
