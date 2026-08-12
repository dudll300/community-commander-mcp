from __future__ import annotations

import os
from datetime import date

import pytest

from community_commander.application.product_insights import ProductInsightsService
from community_commander.application.ticket_context import TicketContextService
from community_commander.config import Settings
from community_commander.infrastructure.graph_api import GraphApiClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_graph_api_ticket_context_smoke() -> None:
    if os.getenv("RUN_GRAPH_API_SMOKE") != "1" or not os.getenv("GRAPH_API_TOKEN"):
        pytest.skip("set RUN_GRAPH_API_SMOKE=1 and GRAPH_API_TOKEN to enable")

    settings = Settings.from_env()
    async with GraphApiClient(settings) as graph_api:
        ticket_context = await TicketContextService(graph_api).get_ticket_context("ticket-0001", 5)
        assert ticket_context.products
        product_id = ticket_context.products[0].id
        insights = ProductInsightsService(graph_api)
        overview = await insights.get_community_overview(
            product_id, date(2026, 1, 1), date(2026, 12, 31)
        )
        owners = await insights.find_product_owners(product_id)

    assert ticket_context.ticket.id == "ticket-0001"
    assert overview.product.id == product_id
    assert len(overview.metrics) == 5
    assert owners.product.id == product_id
