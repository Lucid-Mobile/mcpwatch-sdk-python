"""HTTP client for sending events to the MCPWatch ingestion API."""

from __future__ import annotations

import asyncio
import logging
import sys

import httpx

from mcpwatch.types import IngestRequest, IngestResponse, McpWatchEvent, SdkInfo

logger = logging.getLogger("mcpwatch")

DEFAULT_ENDPOINT = "https://ingest.mcpwatch.dev"
SDK_NAME = "mcpwatch-python"
SDK_VERSION = "0.1.0"

# Retry configuration
MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 10.0


class MCPWatchClient:
    """HTTP client that sends batched events to the MCPWatch ingestion API."""

    def __init__(self, api_key: str, endpoint: str = DEFAULT_ENDPOINT, debug: bool = False):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.debug = debug
        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

    async def send_batch(self, events: list[McpWatchEvent]) -> IngestResponse | None:
        """Send a batch of events to the ingestion API.

        On failure, retries once after a 1-second delay.  If the retry also
        fails the batch is silently dropped so SDK usage never blocks the
        host MCP server.
        """
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

        last_error: Exception | None = None

        for attempt in range(1 + MAX_RETRIES):
            try:
                response = await self._client.post(
                    f"{self.endpoint}/v1/events",
                    content=request.model_dump_json(),
                )

                if response.status_code == 202:
                    result = IngestResponse.model_validate_json(response.content)
                    if self.debug:
                        logger.info(f"Sent {result.accepted} events")
                    return result

                # Retry on server errors (5xx); give up immediately on client errors (4xx)
                if response.status_code >= 500 and attempt < MAX_RETRIES:
                    if self.debug:
                        logger.warning(
                            f"Server error {response.status_code} on attempt {attempt + 1}, "
                            f"retrying in {RETRY_DELAY_SECONDS}s"
                        )
                    last_error = Exception(f"HTTP {response.status_code}: {response.text}")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                if self.debug:
                    logger.error(f"Ingestion failed: {response.status_code} {response.text}")
                return None

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    if self.debug:
                        logger.warning(
                            f"Send attempt {attempt + 1} failed ({e}), retrying in {RETRY_DELAY_SECONDS}s"
                        )
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        # All attempts exhausted -- drop the batch
        if self.debug and last_error is not None:
            logger.error(f"Failed to send events after {1 + MAX_RETRIES} attempts: {last_error}")
        return None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
