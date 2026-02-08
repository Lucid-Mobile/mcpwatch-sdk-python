"""Async event batcher for MCPWatch SDK."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from mcpwatch.client import MCPWatchClient
from mcpwatch.types import McpWatchEvent

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
    ):
        self._client = MCPWatchClient(api_key=api_key, endpoint=endpoint, debug=debug)
        self._queue: list[McpWatchEvent] = []
        self._max_batch_size = max_batch_size
        self._flush_interval = flush_interval
        self._debug = debug
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

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
        if len(self._queue) >= MAX_PENDING_EVENTS:
            # Drop oldest events
            drop_count = len(self._queue) - MAX_PENDING_EVENTS + 1
            self._queue = self._queue[drop_count:]
            if self._debug:
                logger.warning(f"Event queue full, dropped {drop_count} oldest events")

        self._queue.append(event)

        if len(self._queue) >= self._max_batch_size:
            # Schedule an immediate flush if an event loop is running
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self.flush())
            except RuntimeError:
                pass  # No running event loop, timer flush will handle it

    async def flush(self) -> None:
        """Flush pending events to the ingestion API."""
        if not self._queue:
            return

        batch = self._queue[: self._max_batch_size]
        self._queue = self._queue[self._max_batch_size :]

        await self._client.send_batch(batch)

    async def shutdown(self) -> None:
        """Flush remaining events and stop the batcher."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        while self._queue:
            await self.flush()

        await self._client.close()
