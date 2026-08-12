from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SERVER = Path(__file__).with_name("stdio_fixture_server.py")


@pytest.mark.asyncio
async def test_real_stdio_handshake_discovery_and_tool_call() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(FIXTURE_SERVER)],
        cwd=PROJECT_ROOT,
        env={"LOG_LEVEL": "ERROR"},
    )
    with tempfile.TemporaryFile(mode="w+") as stderr:
        async with stdio_client(parameters, errlog=stderr) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == [
                    "get_ticket_context",
                    "get_community_overview",
                    "investigate_product_issue",
                    "find_product_owners",
                ]
                assert all(tool.output_schema is not None for tool in tools.tools)

                result = await session.call_tool(
                    "get_ticket_context", {"ticket_id": "ticket-1", "comments_limit": 1}
                )
                invalid_result = await session.call_tool(
                    "get_ticket_context", {"ticket_id": "ticket-1", "comments_limit": 0}
                )
                overview_result = await session.call_tool(
                    "get_community_overview",
                    {
                        "product_id": "product-1",
                        "from_date": "2026-01-01",
                        "to_date": "2026-12-31",
                    },
                )
                owners_result = await session.call_tool(
                    "find_product_owners", {"product_id": "product-1"}
                )
        stderr.seek(0)
        stderr_output = stderr.read()

    assert result.is_error is False
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.startswith("Ticket ticket-1: Game crashes on startup")
    assert result.structured_content is not None
    assert result.structured_content["truncated"] == {"comments": True}
    assert [item["id"] for item in result.structured_content["comments"]] == ["comment-1"]
    assert "email" not in result.structured_content["assignees"][0]
    assert "email" not in result.structured_content["opened_by"][0]
    assert invalid_result.is_error is True
    assert overview_result.is_error is False
    assert overview_result.structured_content is not None
    assert overview_result.structured_content["tickets"]["total"] == 1
    assert owners_result.is_error is False
    assert owners_result.structured_content is not None
    assert "email" not in owners_result.structured_content["contributors"][0]["employee"]
    assert "Traceback" not in stderr_output
