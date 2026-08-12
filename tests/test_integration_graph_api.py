from __future__ import annotations

import os

import pytest

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
        result = await TicketContextService(graph_api).get_ticket_context("ticket-0001", 5)

    assert result.ticket.id == "ticket-0001"
