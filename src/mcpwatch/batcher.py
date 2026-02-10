"""Async event batcher for MCPWatch SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from mcpwatch.client import MCPWatchClient, SendResult
from mcpwatch.types import McpWatchEvent, QuotaInfo

if TYPE_CHECKING:
    pass

logger = logging.getLogger("mcpwatch")

MAX_PENDING_EVENTS = 1000


class EventBatcher:
    """Accumulates events and flushes them in batches."""

    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://ingest.mcpwatch.dev",
        debug: bool = False,
        max_batch_size: int = 50,
        flush_interval: float = 1.0,
        on_quota_warning: Callable[[QuotaInfo], None] | None = None,
    ):
        self._client = MCPWatchClient(
            api_key=api_key,
            endpoint=endpoint,
            debug=debug,
            on_quota_warning=on_quota_warning,
        )
        self._queue: list[McpWatchEvent] = []
        self._max_batch_size = max_batch_size
        self._flush_interval = flush_interval
        self._debug = debug
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False
        self._paused = False
        self._exceeded_warned = False

    @property
    def quota_status(self) -> QuotaInfo | None:
        """Current quota status from the last server response."""
        return self._client.quota_status

    def start(self) -> None:
        """Start the background flush timer."""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        """Periodically flush events."""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            await self.flush()

    def add(self, event: McpWatchEvent) -> None:
        """Add an event to the batch queue."""
        if self._paused:
            if self._debug:
                logger.warning("Quota hard limit active, dropping event")
            return

        if len(self._queue) >= MAX_PENDING_EVENTS:
            drop_count = len(self._queue) - MAX_PENDING_EVENTS + 1
            self._queue = self._queue[drop_count:]
            if self._debug:
                logger.warning("Event queue full, dropped %d oldest events", drop_count)

        self._queue.append(event)

        if len(self._queue) >= self._max_batch_size:
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self.flush())
            except RuntimeError:
                pass

    async def flush(self) -> None:
        """Flush pending events to the ingestion API."""
        if not self._queue or self._paused:
            return

        batch = self._queue[: self._max_batch_size]
        self._queue = self._queue[self._max_batch_size :]

        result: SendResult = await self._client.send_batch(batch)

        if result.retry_after:
            self._paused = True
            logger.warning(
                "Quota hard limit reached. Pausing event ingestion for %ds",
                result.retry_after,
            )
            await self._pause_for(result.retry_after)

        if result.quota_info and result.quota_info.status == "exceeded" and not self._exceeded_warned:
            self._exceeded_warned = True
            logger.warning(
                "Quota exceeded — events are still being accepted in the grace period "
                "but will be hidden in the dashboard"
            )

    async def _pause_for(self, seconds: int) -> None:
        """Pause ingestion for the specified duration, then resume."""
        await asyncio.sleep(seconds)
        self._paused = False
        self._exceeded_warned = False
        if self._debug:
            logger.info("Quota pause lifted, resuming event ingestion")

    async def shutdown(self) -> None:
        """Flush remaining events and stop the batcher."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        self._paused = False
        while self._queue:
            await self.flush()

        await self._client.close()
