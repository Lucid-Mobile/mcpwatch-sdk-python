"""Event type definitions for MCPWatch SDK."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    TOOL_CALL = "tool_call"
    RESOURCE_READ = "resource_read"
    PROMPT_GET = "prompt_get"
    INITIALIZE = "initialize"
    CLOSE = "close"
    NOTIFICATION = "notification"
    ERROR = "error"


class McpWatchEvent(BaseModel):
    event_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    event_type: EventType
    event_name: str
    started_at: str
    ended_at: str | None = None
    duration_ms: float = 0.0
    mcp_method: str
    mcp_protocol_version: str = "2025-11-25"
    request_params: dict[str, Any] = Field(default_factory=dict)
    response_content: dict[str, Any] = Field(default_factory=dict)
    is_error: bool = False
    error_code: int | None = None
    error_message: str | None = None
    transport_type: str = ""
    server_name: str = ""
    server_version: str = ""
    client_name: str = ""
    client_version: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)
    sdk_name: str = "mcpwatch-python"
    sdk_version: str = "1.0.0"


class SdkInfo(BaseModel):
    name: str = "mcpwatch-python"
    version: str = "1.0.0"
    runtime: str = "python"
    runtime_version: str = ""


class IngestRequest(BaseModel):
    batch: list[McpWatchEvent]
    sdk: SdkInfo = Field(default_factory=SdkInfo)


class QuotaInfo(BaseModel):
    limit: int
    remaining: int
    status: str  # "ok" | "warning" | "exceeded" | "hard_limit"
    reset: str


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    quota: QuotaInfo | None = None


class MCPWatchConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: str
    endpoint: str = "https://ingest.mcpwatch.dev"
    debug: bool = False
    sample_rate: float = 1.0
    max_batch_size: int = 50
    flush_interval: float = 1.0
    on_quota_warning: Callable[[QuotaInfo], None] | None = None
