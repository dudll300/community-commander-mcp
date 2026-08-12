# Community Commander MCP

Read-only MCP server that assembles the full context of a community support ticket from the
Hackathon Neo4j graph API.

The first release exposes one tool:

```text
get_ticket_context(ticket_id: str, comments_limit: int = 50)
```

It returns the ticket, related products, assignees, opener, ordered comments, partial-data
warnings, and truncation metadata. Account and employee email addresses are intentionally
excluded from MCP output.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- A bearer token for the graph API

## Install and run

```bash
uv sync --no-editable
GRAPH_API_TOKEN=your-token uv run --no-sync community-commander-mcp
```

The process uses MCP over stdin/stdout. Logs go to stderr so they cannot corrupt the protocol.

Supported environment variables:

| Variable | Required | Default |
| --- | --- | --- |
| `GRAPH_API_TOKEN` | yes | — |
| `GRAPH_API_BASE_URL` | no | URL from `openapi.json` |
| `GRAPH_API_TIMEOUT_SECONDS` | no | `10` |
| `LOG_LEVEL` | no | `INFO` |

## MCP client configuration

Use an absolute path to `uv` and this repository in production client configuration:

```json
{
  "mcpServers": {
    "community-commander": {
      "command": "/opt/homebrew/bin/uv",
      "args": [
        "--directory",
        "/absolute/path/to/hackathon",
        "run",
        "--no-sync",
        "community-commander-mcp"
      ],
      "env": {
        "GRAPH_API_TOKEN": "your-token"
      }
    }
  }
}
```

Prefer injecting `GRAPH_API_TOKEN` from the client's secret storage instead of committing it to
a configuration file.

## Development

```bash
uv sync --no-editable
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest
```

An optional real-API smoke test runs only when `GRAPH_API_TOKEN` is present:

```bash
RUN_GRAPH_API_SMOKE=1 GRAPH_API_TOKEN=your-token uv run --no-sync pytest -m integration
```
