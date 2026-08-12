from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent
from pydantic import Field, StringConstraints

from community_commander.application.ticket_context import (
    TicketContextService,
    summarize_ticket_context,
)
from community_commander.config import Settings
from community_commander.domain.models import TicketContext
from community_commander.infrastructure.graph_api import GraphApiClient


@dataclass(slots=True)
class AppContext:
    ticket_context_service: TicketContextService


@asynccontextmanager
async def app_lifespan(_: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    async with GraphApiClient(settings) as graph_api:
        yield AppContext(ticket_context_service=TicketContextService(graph_api))


Lifespan = Callable[[MCPServer[AppContext]], AbstractAsyncContextManager[AppContext]]


def create_server(lifespan: Lifespan = app_lifespan) -> MCPServer[AppContext]:
    server = MCPServer(
        "community-commander",
        version="0.1.0",
        instructions="Read-only community support investigation tools.",
        lifespan=lifespan,
    )

    @server.tool(
        title="Get ticket context",
        description=(
            "Fetch a support ticket and its related products, assignees, opener, and ordered "
            "comments. Use this before investigating or summarizing a ticket."
        ),
    )
    async def get_ticket_context(
        ticket_id: Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ],
        ctx: Context,
        comments_limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> Annotated[CallToolResult, TicketContext]:
        """Return a privacy-filtered, structured context for one support ticket."""
        app_context: AppContext = ctx.request_context.lifespan_context
        result = await app_context.ticket_context_service.get_ticket_context(
            ticket_id=ticket_id,
            comments_limit=comments_limit,
        )
        return CallToolResult(
            content=[TextContent(type="text", text=summarize_ticket_context(result))],
            structuredContent=result.model_dump(mode="json"),
        )

    return server


mcp = create_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
