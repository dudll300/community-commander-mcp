from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent
from pydantic import Field, StringConstraints

from community_commander.application.product_insights import (
    ProductInsightsService,
    summarize_investigation,
    summarize_overview,
    summarize_owners,
)
from community_commander.application.ticket_context import (
    TicketContextService,
    summarize_ticket_context,
)
from community_commander.config import Settings
from community_commander.domain.models import (
    CommunityOverview,
    ProductIssueInvestigation,
    ProductOwners,
    TicketContext,
)
from community_commander.infrastructure.graph_api import GraphApiClient


@dataclass(slots=True)
class AppContext:
    ticket_context_service: TicketContextService
    product_insights_service: ProductInsightsService


@asynccontextmanager
async def app_lifespan(_: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    async with GraphApiClient(settings) as graph_api:
        yield AppContext(
            ticket_context_service=TicketContextService(graph_api),
            product_insights_service=ProductInsightsService(graph_api),
        )


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

    @server.tool(
        title="Get community overview",
        description=(
            "Summarize product metrics, support tickets, and reviews for an inclusive date range."
        ),
    )
    async def get_community_overview(
        product_id: Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ],
        from_date: date,
        to_date: date,
        ctx: Context,
    ) -> Annotated[CallToolResult, CommunityOverview]:
        app_context: AppContext = ctx.request_context.lifespan_context
        result = await app_context.product_insights_service.get_community_overview(
            product_id, from_date, to_date
        )
        return CallToolResult(
            content=[TextContent(type="text", text=summarize_overview(result))],
            structuredContent=result.model_dump(mode="json"),
        )

    @server.tool(
        title="Investigate product issue",
        description=(
            "Investigate product health signals with daily metrics, relevant tickets, and negative "
            "reviews for an inclusive date range."
        ),
    )
    async def investigate_product_issue(
        product_id: Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ],
        from_date: date,
        to_date: date,
        ctx: Context,
        items_limit: Annotated[int, Field(ge=1, le=100)] = 20,
    ) -> Annotated[CallToolResult, ProductIssueInvestigation]:
        app_context: AppContext = ctx.request_context.lifespan_context
        result = await app_context.product_insights_service.investigate_product_issue(
            product_id, from_date, to_date, items_limit
        )
        return CallToolResult(
            content=[TextContent(type="text", text=summarize_investigation(result))],
            structuredContent=result.model_dump(mode="json"),
        )

    @server.tool(
        title="Find product owners",
        description=(
            "Find projects, owning departments, and privacy-filtered contributors responsible "
            "for a product."
        ),
    )
    async def find_product_owners(
        product_id: Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ],
        ctx: Context,
    ) -> Annotated[CallToolResult, ProductOwners]:
        app_context: AppContext = ctx.request_context.lifespan_context
        result = await app_context.product_insights_service.find_product_owners(product_id)
        return CallToolResult(
            content=[TextContent(type="text", text=summarize_owners(result))],
            structuredContent=result.model_dump(mode="json"),
        )

    return server


mcp = create_server()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
