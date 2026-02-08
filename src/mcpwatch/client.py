"""HTTP client for sending events to the MCPWatch ingestion API."""

from __future__ import annotations

import logging
import sys

import httpx

from mcpwatch.types import IngestRequest, IngestResponse, McpWatchEvent, SdkInfo

logger = logging.getLogger("mcpwatch")

DEFAULT_ENDPOINT = "https://ingest.mcpwatch.dev"
SDK_NAME = "mcpwatch-python"
SDK_VERSION = "0.1.0"


class MCPWatchClient:
    """HTTP client that sends batched events to the MCPWatch ingestion API."""

    def __init__(self, api_key: str, endpoint: str = DEFAULT_ENDPOINT, debug: bool = False):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.debug = debug
        self._client = httpx.AsyncClient(
            timeout=10.0,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

    async def send_batch(self, events: list[McpWatchEvent]) -> IngestResponse | None:
        """Send a batch of events to the ingestion API."""
        if not events:
            return None

        request = IngestRequest(
            batch=events,
            sdk=SdkInfo(
                name=SDK_NAME,
                version=SDK_VERSION,
                runtime="python",
                runtime_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            ),
        )

        try:
            response = await self._client.post(
                f"{self.endpoint}/v1/events",
                content=request.model_dump_json(),
            )

            if response.status_code != 202:
                if self.debug:
                    logger.error(f"Ingestion failed: {response.status_code} {response.text}")
                return None

            result = IngestResponse.model_validate_json(response.content)
            if self.debug:
                logger.info(f"Sent {result.accepted} events")
            return result

        except Exception as e:
            if self.debug:
                logger.error(f"Failed to send events: {e}")
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
