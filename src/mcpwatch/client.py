"""HTTP client for sending events to the MCPWatch ingestion API."""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Callable

import httpx

from mcpwatch.types import IngestRequest, IngestResponse, McpWatchEvent, QuotaInfo, SdkInfo

logger = logging.getLogger("mcpwatch")

DEFAULT_ENDPOINT = "https://ingest.mcpwatch.dev"
SDK_NAME = "mcpwatch-python"
SDK_VERSION = "0.1.0"

MAX_RETRIES = 1
RETRY_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 10.0


@dataclass
class SendResult:
    """Result of a batch send, including quota information."""

    response: IngestResponse | None
    quota_info: QuotaInfo | None
    retry_after: int | None


class MCPWatchClient:
    """HTTP client that sends batched events to the MCPWatch ingestion API."""

    def __init__(
        self,
        api_key: str,
        endpoint: str = DEFAULT_ENDPOINT,
        debug: bool = False,
        on_quota_warning: Callable[[QuotaInfo], None] | None = None,
    ):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.debug = debug
        self.on_quota_warning = on_quota_warning
        self._quota_status: QuotaInfo | None = None
        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

    @property
    def quota_status(self) -> QuotaInfo | None:
        """Current quota status from the last server response."""
        return self._quota_status

    def _parse_quota_headers(self, headers: httpx.Headers) -> QuotaInfo | None:
        limit = headers.get("x-mcpwatch-quota-limit")
        status = headers.get("x-mcpwatch-quota-status")
        if not limit or not status:
            return None

        remaining = headers.get("x-mcpwatch-quota-remaining")
        reset = headers.get("x-mcpwatch-quota-reset")

        return QuotaInfo(
            limit=int(limit),
            remaining=int(remaining) if remaining else 0,
            status=status,
            reset=reset or "",
        )

    async def send_batch(self, events: list[McpWatchEvent]) -> SendResult:
        """Send a batch of events to the ingestion API."""
        if not events:
            return SendResult(response=None, quota_info=None, retry_after=None)

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

                quota_info = self._parse_quota_headers(response.headers)
                if quota_info:
                    self._quota_status = quota_info
                    if quota_info.status in ("warning", "exceeded"):
                        logger.warning(
                            "Quota %s: %d events remaining (limit: %d)",
                            quota_info.status,
                            quota_info.remaining,
                            quota_info.limit,
                        )
                        if self.on_quota_warning:
                            self.on_quota_warning(quota_info)

                if response.status_code == 429:
                    retry_after_hdr = response.headers.get("retry-after", "60")
                    retry_after = int(retry_after_hdr)
                    logger.warning("Quota hard limit reached. Retry after %ds", retry_after)
                    return SendResult(response=None, quota_info=quota_info, retry_after=retry_after)

                if response.status_code == 202:
                    result = IngestResponse.model_validate_json(response.content)
                    if self.debug:
                        logger.info("Sent %d events", result.accepted)
                    return SendResult(response=result, quota_info=quota_info, retry_after=None)

                if response.status_code >= 500 and attempt < MAX_RETRIES:
                    if self.debug:
                        logger.warning(
                            "Server error %d on attempt %d, retrying in %ss",
                            response.status_code,
                            attempt + 1,
                            RETRY_DELAY_SECONDS,
                        )
                    last_error = Exception(f"HTTP {response.status_code}: {response.text}")
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                if self.debug:
                    logger.error("Ingestion failed: %d %s", response.status_code, response.text)
                return SendResult(response=None, quota_info=quota_info, retry_after=None)

            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    if self.debug:
                        logger.warning(
                            "Send attempt %d failed (%s), retrying in %ss",
                            attempt + 1,
                            e,
                            RETRY_DELAY_SECONDS,
                        )
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        if self.debug and last_error is not None:
            logger.error("Failed to send events after %d attempts: %s", 1 + MAX_RETRIES, last_error)
        return SendResult(response=None, quota_info=None, retry_after=None)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
