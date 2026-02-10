"""Tests for MCPWatchClient."""

import pytest
from mcpwatch.client import MCPWatchClient


def test_client_creation():
    client = MCPWatchClient(api_key="mw_test_key")
    assert client is not None


def test_client_custom_endpoint():
    client = MCPWatchClient(api_key="mw_test_key", endpoint="http://localhost:8080")
    assert client.endpoint == "http://localhost:8080"


@pytest.mark.asyncio
async def test_send_empty_batch():
    client = MCPWatchClient(api_key="mw_test_key")
    result = await client.send_batch([])
    assert result.response is None
    assert result.quota_info is None
    assert result.retry_after is None
    await client.close()
