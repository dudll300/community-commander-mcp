from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from community_commander.application.ticket_context import TicketContextService
from community_commander.domain.models import Account, Comment, Edge, Employee, Product, Ticket
from community_commander.server import AppContext, create_server


class FixtureGraphApi:
    async def get_ticket(self, ticket_id: str) -> Ticket:
        return Ticket(
            id=ticket_id,
            subject="Game crashes on startup",
            category="bug",
            status="open",
            priority="high",
            opened_at="2026-08-10T10:00:00Z",
        )

    async def get_product(self, product_id: str) -> Product:
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

    async def get_employee(self, employee_id: str) -> Employee:
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

    async def get_account(self, account_id: str) -> Account:
        return Account(
            id=account_id,
            email="player@example.test",
            display_name="Player One",
            country="GB",
            status="active",
            created_at="2025-01-01T00:00:00Z",
        )

    async def get_comment(self, comment_id: str) -> Comment:
        sequence = 1 if comment_id == "comment-1" else 2
        return Comment(
            id=comment_id,
            body=f"Comment {sequence}",
            author_kind="account" if sequence == 1 else "employee",
            sequence=sequence,
            created_at=f"2026-08-10T10:0{sequence}:00Z",
        )

    async def list_relationships(
        self,
        relationship: str,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[Edge]:
        ticket_id = from_id or to_id or "ticket-1"
        targets = {
            "concerns": [(ticket_id, "product-1")],
            "assigned-to": [(ticket_id, "employee-1")],
            "has-comment": [(ticket_id, "comment-2"), (ticket_id, "comment-1")],
            "opened": [("account-1", ticket_id)],
        }
        return [
            Edge.model_validate({"from": source, "to": target})
            for source, target in targets[relationship]
        ]


@asynccontextmanager
async def fixture_lifespan(_: object) -> AsyncIterator[AppContext]:
    yield AppContext(ticket_context_service=TicketContextService(FixtureGraphApi()))


if __name__ == "__main__":
    create_server(fixture_lifespan).run()
