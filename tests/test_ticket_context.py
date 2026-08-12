from __future__ import annotations

from typing import cast

import pytest

from community_commander.application.ticket_context import TicketContextService
from community_commander.domain.errors import (
    GraphApiNotFoundError,
    GraphApiUnavailableError,
    InvalidTicketIdError,
    TicketNotFoundError,
)
from community_commander.domain.models import (
    Account,
    Comment,
    Edge,
    Employee,
    Product,
    Ticket,
)


def ticket(ticket_id: str = "ticket-1") -> Ticket:
    return Ticket(
        id=ticket_id,
        subject="Game crashes on startup",
        category="bug",
        status="open",
        priority="high",
        opened_at="2026-08-10T10:00:00Z",
    )


def product(product_id: str = "product-1") -> Product:
    return Product(
        id=product_id,
        title="Graph Quest",
        kind="game",
        genre="rpg",
        platform="pc",
        status="released",
        price_usd=29.99,
        released_at="2026-01-01",
    )


def employee(employee_id: str = "employee-1") -> Employee:
    return Employee(
        id=employee_id,
        name="Ada Lovelace",
        email="ada@example.test",
        title="Senior Engineer",
        grade="L6",
        location="London",
        hired_at="2020-01-01",
        fte=1,
    )


def account(account_id: str = "account-1") -> Account:
    return Account(
        id=account_id,
        email="player@example.test",
        display_name="Player One",
        country="GB",
        status="active",
        created_at="2025-01-01T00:00:00Z",
    )


def comment(comment_id: str, sequence: int) -> Comment:
    return Comment(
        id=comment_id,
        body=f"Comment {sequence}",
        author_kind="account",
        sequence=sequence,
        created_at=f"2026-08-10T10:0{sequence}:00Z",
    )


class FakeGraphApi:
    def __init__(self) -> None:
        self.ticket_result: Ticket | Exception = ticket()
        self.relationships: dict[str, list[Edge] | Exception] = {
            "concerns": [Edge.model_validate({"from": "ticket-1", "to": "product-1"})],
            "assigned-to": [Edge.model_validate({"from": "ticket-1", "to": "employee-1"})],
            "has-comment": [
                Edge.model_validate({"from": "ticket-1", "to": "comment-2"}),
                Edge.model_validate({"from": "ticket-1", "to": "comment-1"}),
            ],
            "opened": [Edge.model_validate({"from": "account-1", "to": "ticket-1"})],
        }
        self.products: dict[str, Product | Exception] = {"product-1": product()}
        self.employees: dict[str, Employee | Exception] = {"employee-1": employee()}
        self.accounts: dict[str, Account | Exception] = {"account-1": account()}
        self.comments: dict[str, Comment | Exception] = {
            "comment-1": comment("comment-1", 1),
            "comment-2": comment("comment-2", 2),
        }
        self.calls: list[tuple[str, str]] = []

    async def get_ticket(self, ticket_id: str) -> Ticket:
        self.calls.append(("ticket", ticket_id))
        return _resolve(self.ticket_result)

    async def get_product(self, product_id: str) -> Product:
        self.calls.append(("product", product_id))
        return _resolve(self.products[product_id])

    async def get_employee(self, employee_id: str) -> Employee:
        self.calls.append(("employee", employee_id))
        return _resolve(self.employees[employee_id])

    async def get_account(self, account_id: str) -> Account:
        self.calls.append(("account", account_id))
        return _resolve(self.accounts[account_id])

    async def get_comment(self, comment_id: str) -> Comment:
        self.calls.append(("comment", comment_id))
        return _resolve(self.comments[comment_id])

    async def list_relationships(
        self,
        relationship: str,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[Edge]:
        self.calls.append((relationship, from_id or to_id or ""))
        return _resolve(self.relationships[relationship])


def _resolve[ResultT](value: ResultT | Exception) -> ResultT:
    if isinstance(value, Exception):
        raise value
    return cast(ResultT, value)


@pytest.mark.asyncio
async def test_builds_full_context_orders_comments_and_filters_emails() -> None:
    graph = FakeGraphApi()
    service = TicketContextService(graph)

    result = await service.get_ticket_context(" ticket-1 ", comments_limit=50)

    assert result.ticket.id == "ticket-1"
    assert [item.id for item in result.products] == ["product-1"]
    assert [item.id for item in result.assignees] == ["employee-1"]
    assert [item.id for item in result.opened_by] == ["account-1"]
    assert [item.id for item in result.comments] == ["comment-1", "comment-2"]
    assert "email" not in result.assignees[0].model_dump()
    assert "email" not in result.opened_by[0].model_dump()
    assert result.warnings == []
    assert result.truncated.comments is False


@pytest.mark.asyncio
async def test_empty_relationships_return_empty_collections() -> None:
    graph = FakeGraphApi()
    graph.relationships = {name: [] for name in graph.relationships}

    result = await TicketContextService(graph).get_ticket_context("ticket-1", 50)

    assert result.products == []
    assert result.assignees == []
    assert result.opened_by == []
    assert result.comments == []
    assert result.warnings == []


@pytest.mark.asyncio
async def test_deduplicates_edges_and_marks_comment_truncation() -> None:
    graph = FakeGraphApi()
    graph.relationships["has-comment"].append(  # type: ignore[union-attr]
        Edge.model_validate({"from": "ticket-1", "to": "comment-1"})
    )

    result = await TicketContextService(graph).get_ticket_context("ticket-1", 1)

    assert [item.id for item in result.comments] == ["comment-1"]
    assert result.truncated.comments is True
    assert graph.calls.count(("comment", "comment-1")) == 1


@pytest.mark.asyncio
async def test_returns_partial_result_with_warning_for_related_entity_failure() -> None:
    graph = FakeGraphApi()
    graph.employees["employee-1"] = GraphApiUnavailableError()

    result = await TicketContextService(graph).get_ticket_context("ticket-1", 50)

    assert result.ticket.id == "ticket-1"
    assert result.assignees == []
    assert result.warnings[0].code == "RELATED_ENTITY_UNAVAILABLE"
    assert result.warnings[0].entity_id == "employee-1"


@pytest.mark.asyncio
async def test_returns_partial_result_for_relationship_failure() -> None:
    graph = FakeGraphApi()
    graph.relationships["concerns"] = GraphApiUnavailableError()

    result = await TicketContextService(graph).get_ticket_context("ticket-1", 50)

    assert result.products == []
    assert result.warnings[0].code == "RELATIONSHIP_UNAVAILABLE"
    assert result.warnings[0].entity_id == "concerns"


@pytest.mark.asyncio
async def test_missing_ticket_is_a_hard_error() -> None:
    graph = FakeGraphApi()
    graph.ticket_result = GraphApiNotFoundError("ticket", "missing")

    with pytest.raises(TicketNotFoundError, match="TICKET_NOT_FOUND"):
        await TicketContextService(graph).get_ticket_context("missing", 50)


@pytest.mark.asyncio
async def test_blank_ticket_id_is_rejected_before_api_call() -> None:
    graph = FakeGraphApi()

    with pytest.raises(InvalidTicketIdError, match="INVALID_TICKET_ID"):
        await TicketContextService(graph).get_ticket_context("   ", 50)

    assert graph.calls == []
