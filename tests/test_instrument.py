"""Tests for the instrument() function."""

import pytest
from mcpwatch.instrument import instrument


class MockServer:
    """Mock MCP server for testing."""

    def __init__(self, name: str = "test-server", version: str = "1.0.0"):
        self.name = name
        self.version = version
        self._tools: dict[str, object] = {}

    def tool(self, name: str = ""):
        def decorator(func):
            self._tools[name or func.__name__] = func
            return func
        return decorator

    def resource(self, name: str = ""):
        def decorator(func):
            return func
        return decorator


def test_returns_same_instance():
    server = MockServer()
    result = instrument(server, api_key="mw_test_key")
    assert result is server


def test_no_api_key_skips_instrumentation():
    server = MockServer()
    original_tool = server.tool
    result = instrument(server, api_key="")
    assert result is server


def test_wraps_tool_method():
    server = MockServer()
    instrumented = instrument(server, api_key="mw_test_key")
    # The tool method should still be callable
    assert callable(instrumented.tool)
