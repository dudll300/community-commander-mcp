from __future__ import annotations

import json

import httpx
import pytest

from community_commander.config import Settings
from community_commander.domain.errors import (
    GraphApiAuthenticationError,
    GraphApiResponseError,
    GraphApiUnavailableError,
)
from community_commander.infrastructure.graph_api import GraphApiClient

BASE_URL = "https://graph.example.test"


def settings(token: str = "top-secret") -> Settings:
    return Settings(graph_api_token=token, graph_api_base_url=BASE_URL)


@pytest.mark.asyncio
async def test_sends_bearer_token_and_parses_ticket() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer top-secret"
        assert request.extensions["timeout"] == {
            "connect": 10.0,
            "read": 10.0,
            "write": 10.0,
            "pool": 10.0,
        }
        return httpx.Response(
            200,
            json={
                "id": "ticket-1",
                "subject": "Crash",
                "category": "bug",
                "status": "open",
                "priority": "high",
                "opened_at": "2026-08-10T10:00:00Z",
            },
        )

    async with GraphApiClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = await client.get_ticket("ticket-1")

    assert result.id == "ticket-1"


@pytest.mark.asyncio
async def test_escapes_entity_id_as_one_path_segment() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == b"/v1/nodes/tickets/ticket%2F1"
        return httpx.Response(
            200,
            json={
                "id": "ticket/1",
                "subject": "Crash",
                "category": "bug",
                "status": "open",
                "priority": "high",
                "opened_at": "2026-08-10T10:00:00Z",
            },
        )

    async with GraphApiClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = await client.get_ticket("ticket/1")

    assert result.id == "ticket/1"


@pytest.mark.asyncio
async def test_paginates_relationships_until_cursor_is_absent() -> None:
    cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        cursors.append(cursor)
        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "count": 2,
                    "limit": 500,
                    "offset": 0,
                    "items": [{"from": "ticket-1", "to": "comment-1"}],
                    "next_cursor": "next",
                },
            )
        return httpx.Response(
            200,
            json={
                "count": 2,
                "limit": 500,
                "offset": 1,
                "items": [{"from": "ticket-1", "to": "comment-2"}],
            },
        )

    async with GraphApiClient(settings(), transport=httpx.MockTransport(handler)) as client:
        result = await client.list_relationships("has-comment", from_id="ticket-1")

    assert [edge.to_id for edge in result] == ["comment-1", "comment-2"]
    assert cursors == [None, "next"]


@pytest.mark.asyncio
async def test_retries_429_and_uses_retry_after() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(429, headers={"Retry-After": "0.1"})
        return httpx.Response(
            200,
            json={
                "id": "ticket-1",
                "subject": "Crash",
                "category": "bug",
                "status": "open",
                "priority": "high",
                "opened_at": "2026-08-10T10:00:00Z",
            },
        )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with GraphApiClient(
        settings(), transport=httpx.MockTransport(handler), sleep=fake_sleep
    ) as client:
        await client.get_ticket("ticket-1")

    assert attempts == 3
    assert sleeps == [0.1, 0.1]


@pytest.mark.asyncio
async def test_retries_server_errors_then_returns_sanitized_error() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="secret upstream diagnostics")

    async def no_sleep(_: float) -> None:
        return None

    async with GraphApiClient(
        settings(), transport=httpx.MockTransport(handler), sleep=no_sleep
    ) as client:
        with pytest.raises(GraphApiUnavailableError) as error:
            await client.get_ticket("ticket-1")

    assert attempts == 3
    assert "secret upstream diagnostics" not in str(error.value)
    assert "top-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_retries_network_errors() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection failed with top-secret", request=request)

    async def no_sleep(_: float) -> None:
        return None

    async with GraphApiClient(
        settings(), transport=httpx.MockTransport(handler), sleep=no_sleep
    ) as client:
        with pytest.raises(GraphApiUnavailableError) as error:
            await client.get_ticket("ticket-1")

    assert attempts == 3
    assert "top-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_does_not_retry_regular_4xx() -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json={"error": "bad filter"})

    async with GraphApiClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GraphApiUnavailableError):
            await client.get_ticket("ticket-1")

    assert attempts == 1


@pytest.mark.asyncio
async def test_authentication_error_is_specific_and_sanitized() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text="token top-secret"))

    async with GraphApiClient(settings(), transport=transport) as client:
        with pytest.raises(GraphApiAuthenticationError) as error:
            await client.get_ticket("ticket-1")

    assert str(error.value) == "GRAPH_API_AUTH_FAILED: check GRAPH_API_TOKEN"


@pytest.mark.asyncio
async def test_invalid_json_is_rejected() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, content=b"not-json", headers={"Content-Type": "text/plain"})
    )

    async with GraphApiClient(settings(), transport=transport) as client:
        with pytest.raises(GraphApiResponseError):
            await client.get_ticket("ticket-1")


@pytest.mark.asyncio
async def test_repeated_cursor_is_rejected() -> None:
    payload = json.dumps(
        {"count": 2, "limit": 500, "offset": 0, "items": [], "next_cursor": "same"}
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=payload))

    async with GraphApiClient(settings(), transport=transport) as client:
        with pytest.raises(GraphApiResponseError):
            await client.list_relationships("concerns", from_id="ticket-1")
