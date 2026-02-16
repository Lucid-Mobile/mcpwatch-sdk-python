# mcpwatch

Observability SDK for MCP servers. Captures tool calls, resource reads, prompts, and lifecycle events with zero configuration.

## Installation

```bash
pip install mcpwatch
```

## Quick Start

```python
import os
from mcp.server import Server
from mcpwatch import instrument

server = instrument(
    Server("my-server"),
    api_key=os.environ["MCPWATCH_API_KEY"],
    endpoint="https://api.mcpwatch.dev",
)

# Define tools as usual — they're automatically instrumented
@server.tool("get_weather")
async def get_weather(city: str) -> str:
    return f"Weather in {city}: 72°F"
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str` | — | **Required.** Your MCPWatch API key |
| `endpoint` | `str` | `https://api.mcpwatch.dev` | Ingestion endpoint URL |
| `debug` | `bool` | `False` | Enable debug logging |
| `sample_rate` | `float` | `1.0` | Event sampling rate (0.0–1.0) |
| `max_batch_size` | `int` | `50` | Max events per batch |
| `flush_interval` | `float` | `1.0` | Flush interval in seconds |
| `on_quota_warning` | `Callable` | `None` | Callback when quota is approaching limits |

## Examples

See the [examples/](./examples/) directory for complete working examples.

## Requirements

- Python 3.10+

## License

[MIT License](./LICENSE)
