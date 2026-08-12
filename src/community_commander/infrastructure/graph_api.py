from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

from community_commander.config import Settings
from community_commander.domain.errors import (
    GraphApiAuthenticationError,
    GraphApiNotFoundError,
    GraphApiResponseError,
    GraphApiUnavailableError,
)
from community_commander.domain.models import (
    Account,
    Comment,
    Edge,
    Employee,
    Product,
    RelationshipPage,
    Ticket,
)

RelationshipName = Literal["concerns", "assigned-to", "has-comment", "opened"]
ModelT = TypeVar("ModelT", bound=BaseModel)
Sleep = Callable[[float], Awaitable[None]]


class GraphApiClient:
    """Narrow, read-only adapter for the graph endpoints used by ticket context."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.graph_api_base_url,
            headers={"Authorization": f"Bearer {settings.graph_api_token}"},
            timeout=settings.graph_api_timeout_seconds,
            transport=transport,
        )
        self._sleep = sleep
        self._semaphore = asyncio.Semaphore(8)

    async def __aenter__(self) -> GraphApiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_ticket(self, ticket_id: str) -> Ticket:
        return await self._get_model(
            f"/v1/nodes/tickets/{_path_segment(ticket_id)}", Ticket, "ticket", ticket_id
        )

    async def get_product(self, product_id: str) -> Product:
        return await self._get_model(
            f"/v1/nodes/products/{_path_segment(product_id)}", Product, "product", product_id
        )

    async def get_comment(self, comment_id: str) -> Comment:
        return await self._get_model(
            f"/v1/nodes/comments/{_path_segment(comment_id)}", Comment, "comment", comment_id
        )

    async def get_employee(self, employee_id: str) -> Employee:
        return await self._get_model(
            f"/v1/nodes/employees/{_path_segment(employee_id)}", Employee, "employee", employee_id
        )

    async def get_account(self, account_id: str) -> Account:
        return await self._get_model(
            f"/v1/nodes/accounts/{_path_segment(account_id)}", Account, "account", account_id
        )

    async def list_relationships(
        self,
        relationship: RelationshipName,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[Edge]:
        items: list[Edge] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()

        while True:
            params: dict[str, str | int] = {"limit": 500}
            if from_id is not None:
                params["from"] = from_id
            if to_id is not None:
                params["to"] = to_id
            if cursor is not None:
                params["cursor"] = cursor

            payload = await self._request_json(
                "GET", f"/v1/relationships/{relationship}", params=params
            )
            try:
                page = RelationshipPage.model_validate(payload)
            except ValidationError as exc:
                raise GraphApiResponseError() from exc
            items.extend(page.items)

            cursor = page.next_cursor
            if cursor is None:
                return items
            if cursor in seen_cursors:
                raise GraphApiResponseError()
            seen_cursors.add(cursor)

    async def _get_model(
        self,
        path: str,
        model: type[ModelT],
        entity_type: str,
        entity_id: str,
    ) -> ModelT:
        try:
            payload = await self._request_json("GET", path)
        except _NotFound as exc:
            raise GraphApiNotFoundError(entity_type, entity_id) from exc
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise GraphApiResponseError() from exc

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
    ) -> Any:
        for attempt in range(3):
            try:
                async with self._semaphore:
                    response = await self._client.request(method, path, params=params)
            except httpx.RequestError as exc:
                if attempt == 2:
                    raise GraphApiUnavailableError() from exc
                await self._sleep(self._backoff(attempt))
                continue

            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except ValueError as exc:
                    raise GraphApiResponseError() from exc
            if response.status_code == 404:
                raise _NotFound
            if response.status_code in {401, 403}:
                raise GraphApiAuthenticationError()
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    raise GraphApiUnavailableError()
                retry_after = self._retry_after(response)
                delay = retry_after if retry_after is not None else self._backoff(attempt)
                await self._sleep(delay)
                continue
            raise GraphApiUnavailableError()

        raise GraphApiUnavailableError()  # pragma: no cover

    @staticmethod
    def _backoff(attempt: int) -> float:
        return 0.25 * (2**attempt)

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return min(max(float(value), 0.0), 5.0)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                seconds = (retry_at - datetime.now(UTC)).total_seconds()
                return min(max(seconds, 0.0), 5.0)
            except (TypeError, ValueError, OverflowError):
                return None


class _NotFound(Exception):
    pass


def _path_segment(value: str) -> str:
    return quote(value, safe="")
