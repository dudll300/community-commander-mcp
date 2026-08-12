from __future__ import annotations

from datetime import date

import pytest

from community_commander.application.product_insights import ProductInsightsService
from community_commander.domain.errors import (
    GraphApiNotFoundError,
    GraphApiUnavailableError,
    InvalidDateRangeError,
    ProductNotFoundError,
)
from community_commander.domain.models import (
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


class FakeProductGraphApi:
    def __init__(self) -> None:
        self.metrics: dict[str, MetricAggregate | Exception] = {
            measure: _metric(measure, value)
            for measure, value in {
                "active_users": 100,
                "installs": 20,
                "revenue_usd": 400,
                "crashes": 12,
                "refunds": 3,
            }.items()
        }

    async def get_product(self, product_id: str) -> Product:
        if product_id == "missing":
            raise GraphApiNotFoundError("product", product_id)
        return Product(
            id=product_id,
            title="Endless Orbit",
            kind="Bundle",
            genre="Deckbuilder",
            platform="PC",
            status="Live",
            price_usd=39.99,
            released_at="2026-03-21",
        )

    async def get_ticket(self, ticket_id: str) -> Ticket:
        values = {
            "ticket-1": ("2026-03-11T16:00:00Z", "Open", "Urgent"),
            "ticket-2": ("2026-03-12T16:00:00Z", "Resolved", "Normal"),
            "ticket-old": ("2026-02-01T16:00:00Z", "Open", "High"),
        }
        opened_at, status, priority = values[ticket_id]
        return Ticket(
            id=ticket_id,
            subject=f"Issue {ticket_id}",
            category="Bug",
            status=status,
            priority=priority,
            opened_at=opened_at,
        )

    async def get_review(self, review_id: str) -> Review:
        values = {
            "review-1": (1, "2026-03-13"),
            "review-2": (5, "2026-03-14"),
            "review-old": (1, "2026-02-01"),
        }
        rating, created_at = values[review_id]
        return Review(
            id=review_id,
            rating=rating,
            body=f"Review {review_id}",
            language="en",
            created_at=created_at,
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

    async def get_employee(self, employee_id: str) -> Employee:
        return Employee(
            id=employee_id,
            name="Clara Pavlenko",
            email="clara@example.test",
            title="Junior Mobile Engineer",
            grade="L2",
            location="New York",
            hired_at="2025-01-01",
            fte=1,
        )

    async def aggregate_metric(
        self, measure: str, product_id: str, from_date: str, to_date: str
    ) -> MetricAggregate:
        result = self.metrics[measure]
        if isinstance(result, Exception):
            raise result
        return result

    async def list_relationships(
        self,
        relationship: str,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[Edge]:
        edges: dict[str, list[Edge]] = {
            "concerns": [
                _edge("ticket-1", "product-1"),
                _edge("ticket-2", "product-1"),
                _edge("ticket-old", "product-1"),
            ],
            "reviews": [
                _edge("review-1", "product-1"),
                _edge("review-2", "product-1"),
                _edge("review-old", "product-1"),
            ],
            "delivers": [_edge("project-1", "product-1")],
            "owns": [_edge("department-1", "project-1")],
            "contributes-to": [
                ContributionEdge.model_validate(
                    {
                        "from": "employee-1",
                        "to": "project-1",
                        "props": {"role": "Engineer", "allocation_percent": 80},
                    }
                )
            ],
        }
        return edges[relationship]


@pytest.mark.asyncio
async def test_overview_combines_metrics_tickets_and_reviews_for_period() -> None:
    result = await ProductInsightsService(FakeProductGraphApi()).get_community_overview(
        "product-1", date(2026, 3, 1), date(2026, 3, 31)
    )

    assert {metric.measure: metric.total for metric in result.metrics} == {
        "active_users": 100,
        "installs": 20,
        "revenue_usd": 400,
        "crashes": 12,
        "refunds": 3,
    }
    assert result.tickets.model_dump() == {"total": 2, "unresolved": 1, "high_priority": 1}
    assert result.reviews.model_dump() == {"total": 2, "average_rating": 3.0, "negative": 1}
    assert result.warnings == []


@pytest.mark.asyncio
async def test_overview_keeps_partial_metrics_with_warning() -> None:
    graph = FakeProductGraphApi()
    graph.metrics["crashes"] = GraphApiUnavailableError()

    result = await ProductInsightsService(graph).get_community_overview(
        "product-1", date(2026, 3, 1), date(2026, 3, 31)
    )

    assert "crashes" not in {metric.measure for metric in result.metrics}
    assert result.warnings[0].code == "METRIC_UNAVAILABLE"
    assert result.warnings[0].entity_id == "crashes"


@pytest.mark.asyncio
async def test_investigation_prioritizes_and_truncates_problem_items() -> None:
    result = await ProductInsightsService(FakeProductGraphApi()).investigate_product_issue(
        "product-1", date(2026, 3, 1), date(2026, 3, 31), items_limit=1
    )

    assert [item.id for item in result.relevant_tickets] == ["ticket-1"]
    assert [item.id for item in result.negative_reviews] == ["review-1"]
    assert result.truncated.tickets is True
    assert result.truncated.reviews is False
    assert "12 crashes recorded" in result.signals
    assert "3 refunds recorded" in result.signals


@pytest.mark.asyncio
async def test_product_owners_returns_org_chain_without_email() -> None:
    result = await ProductInsightsService(FakeProductGraphApi()).find_product_owners("product-1")

    assert [item.id for item in result.projects] == ["project-1"]
    assert [item.id for item in result.departments] == ["department-1"]
    assert result.contributors[0].role == "Engineer"
    assert result.contributors[0].allocation_percent == 80
    assert "email" not in result.contributors[0].employee.model_dump()


@pytest.mark.asyncio
async def test_product_not_found_is_a_hard_error() -> None:
    with pytest.raises(ProductNotFoundError, match="PRODUCT_NOT_FOUND"):
        await ProductInsightsService(FakeProductGraphApi()).find_product_owners("missing")


@pytest.mark.asyncio
async def test_invalid_period_is_rejected_before_api_calls() -> None:
    with pytest.raises(InvalidDateRangeError, match="INVALID_DATE_RANGE"):
        await ProductInsightsService(FakeProductGraphApi()).get_community_overview(
            "product-1", date(2026, 4, 1), date(2026, 3, 1)
        )


def _edge(from_id: str, to_id: str) -> Edge:
    return Edge.model_validate({"from": from_id, "to": to_id})


def _metric(measure: str, value: float) -> MetricAggregate:
    return MetricAggregate(
        measure=measure,
        group_by="day",
        total=value,
        rows=[{"key": "2026-03-11", "value": value}],
    )
