from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from community_commander.application.product_insights import ProductInsightsService
from community_commander.application.ticket_context import TicketContextService
from community_commander.domain.models import (
    Account,
    Comment,
    ContributionEdge,
    Department,
    Edge,
    Employee,
    MetricAggregate,
    Product,
    Project,
    Review,
    Ticket,
)
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

    async def get_review(self, review_id: str) -> Review:
        return Review(
            id=review_id,
            rating=1,
            body="The game crashes",
            language="en",
            created_at="2026-03-13",
        )

    async def get_project(self, project_id: str) -> Project:
        return Project(
            id=project_id,
            title="Orbit Live Ops",
            status="Active",
            priority="Critical",
            started_at="2026-01-01",
            target_date="2026-12-31",
        )

    async def get_department(self, department_id: str) -> Department:
        return Department(id=department_id, name="Player Experience")

    async def aggregate_metric(
        self, measure: str, product_id: str, from_date: str, to_date: str
    ) -> MetricAggregate:
        value = 12 if measure == "crashes" else 3 if measure == "refunds" else 100
        return MetricAggregate(
            measure=measure,
            group_by="day",
            total=value,
            rows=[{"key": "2026-03-11", "value": value}],
        )

    async def list_relationships(
        self,
        relationship: str,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[Edge]:
        targets = {
            "concerns": [(from_id or "ticket-1", to_id or "product-1")],
            "assigned-to": [(from_id or "ticket-1", "employee-1")],
            "has-comment": [
                (from_id or "ticket-1", "comment-2"),
                (from_id or "ticket-1", "comment-1"),
            ],
            "opened": [("account-1", to_id or "ticket-1")],
            "reviews": [("review-1", to_id or "product-1")],
            "delivers": [("project-1", to_id or "product-1")],
            "owns": [("department-1", to_id or "project-1")],
        }
        if relationship == "contributes-to":
            return [
                ContributionEdge.model_validate(
                    {
                        "from": "employee-1",
                        "to": to_id or "project-1",
                        "props": {"role": "Engineer", "allocation_percent": 80},
                    }
                )
            ]
        return [
            Edge.model_validate({"from": source, "to": target})
            for source, target in targets[relationship]
        ]


@asynccontextmanager
async def fixture_lifespan(_: object) -> AsyncIterator[AppContext]:
    graph_api = FixtureGraphApi()
    yield AppContext(
        ticket_context_service=TicketContextService(graph_api),
        product_insights_service=ProductInsightsService(graph_api),
    )


if __name__ == "__main__":
    create_server(fixture_lifespan).run()
