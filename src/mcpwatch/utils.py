"""Utility functions for MCPWatch SDK."""

import secrets
import time
from datetime import datetime, timezone


_counter = 0


def generate_id() -> str:
    """Generate a unique event ID."""
    global _counter
    timestamp = hex(int(time.time() * 1000))[2:]
    random_part = secrets.token_hex(8)
    _counter = (_counter + 1) % 1000000
    return f"{timestamp}-{random_part}-{_counter}"


def generate_span_id() -> str:
    """Generate a random span ID."""
    return secrets.token_hex(8)


def generate_trace_id() -> str:
    """Generate a random trace ID."""
    return secrets.token_hex(16)


def now_iso() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def duration_ms(start_time: float) -> float:
    """Calculate duration in milliseconds from a perf_counter start time."""
    return (time.perf_counter() - start_time) * 1000
