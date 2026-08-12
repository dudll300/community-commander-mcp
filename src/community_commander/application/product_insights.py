from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from datetime import date, datetime
from typing import Protocol, cast

from community_commander.domain.errors import (
    GraphApiNotFoundError,
    InvalidDateRangeError,
    ProductNotFoundError,
)
from community_commander.domain.models import (
    CommunityOverview,
    ContextWarning,
    ContributionEdge,
    Contributor,
    Department,
    Edge,
    Employee,
    InvestigationTruncation,
    MetricAggregate,
    MetricPoint,
    MetricSeries,
    Product,
    ProductIssueInvestigation,
    ProductOwners,
    Project,
    PublicEmployee,
    Review,
    ReviewSummary,
    Ticket,
    TicketSummary,
)
from community_commander.infrastructure.graph_api import RelationshipName

MEASURES = ("active_users", "installs", "revenue_usd", "crashes", "refunds")


class ProductGraphApi(Protocol):
    async def get_product(self, product_id: str) -> Product: ...

    async def get_ticket(self, ticket_id: str) -> Ticket: ...

    async def get_review(self, review_id: str) -> Review: ...

    async def get_project(self, project_id: str) -> Project: ...

    async def get_department(self, department_id: str) -> Department: ...

    async def get_employee(self, employee_id: str) -> Employee: ...

    async def aggregate_metric(
        self, measure: str, product_id: str, from_date: str, to_date: str
    ) -> MetricAggregate: ...

    async def list_relationships(
        self,
        relationship: RelationshipName,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[Edge]: ...


class ProductInsightsService:
    def __init__(self, graph_api: ProductGraphApi) -> None:
        self._graph_api = graph_api

    async def get_community_overview(
        self, product_id: str, from_date: date, to_date: date
    ) -> CommunityOverview:
        _validate_period(from_date, to_date)
        product = await self._get_product(product_id)
        from_value, to_value = from_date.isoformat(), to_date.isoformat()

        relationship_results, metric_results = await asyncio.gather(
            asyncio.gather(
                self._graph_api.list_relationships("concerns", to_id=product.id),
                self._graph_api.list_relationships("reviews", to_id=product.id),
                return_exceptions=True,
            ),
            asyncio.gather(
                *(
                    self._graph_api.aggregate_metric(measure, product.id, from_value, to_value)
                    for measure in MEASURES
                ),
                return_exceptions=True,
            ),
        )

        warnings: list[ContextWarning] = []
        concern_edges = _relationship_or_warning(relationship_results[0], "concerns", warnings)
        review_edges = _relationship_or_warning(relationship_results[1], "reviews", warnings)

        tickets, ticket_warnings = await _fetch_entities(
            _unique(edge.from_id for edge in concern_edges), "ticket", self._graph_api.get_ticket
        )
        reviews, review_warnings = await _fetch_entities(
            _unique(edge.from_id for edge in review_edges), "review", self._graph_api.get_review
        )
        warnings.extend(ticket_warnings)
        warnings.extend(review_warnings)
        tickets = [item for item in tickets if _in_period(item.opened_at, from_date, to_date)]
        reviews = [item for item in reviews if _in_period(item.created_at, from_date, to_date)]

        metrics: list[MetricSeries] = []
        for measure, result in zip(MEASURES, metric_results, strict=True):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                warnings.append(
                    ContextWarning(
                        code="METRIC_UNAVAILABLE",
                        message=f"Could not load {measure} metrics",
                        entity_type="metric",
                        entity_id=measure,
                    )
                )
                continue
            metrics.append(_metric_series(result))

        negative_reviews = [review for review in reviews if review.rating <= 2]
        return CommunityOverview(
            product=product,
            from_date=from_value,
            to_date=to_value,
            metrics=metrics,
            tickets=TicketSummary(
                total=len(tickets),
                unresolved=sum(ticket.status not in {"Resolved", "Closed"} for ticket in tickets),
                high_priority=sum(ticket.priority in {"Urgent", "High"} for ticket in tickets),
            ),
            reviews=ReviewSummary(
                total=len(reviews),
                average_rating=(
                    round(sum(review.rating for review in reviews) / len(reviews), 2)
                    if reviews
                    else None
                ),
                negative=len(negative_reviews),
            ),
            warnings=warnings,
        )

    async def investigate_product_issue(
        self,
        product_id: str,
        from_date: date,
        to_date: date,
        items_limit: int,
    ) -> ProductIssueInvestigation:
        overview = await self.get_community_overview(product_id, from_date, to_date)
        concern_edges, review_edges = await asyncio.gather(
            self._graph_api.list_relationships("concerns", to_id=overview.product.id),
            self._graph_api.list_relationships("reviews", to_id=overview.product.id),
        )
        tickets, _ = await _fetch_entities(
            _unique(edge.from_id for edge in concern_edges), "ticket", self._graph_api.get_ticket
        )
        reviews, _ = await _fetch_entities(
            _unique(edge.from_id for edge in review_edges), "review", self._graph_api.get_review
        )
        tickets = sorted(
            (ticket for ticket in tickets if _in_period(ticket.opened_at, from_date, to_date)),
            key=lambda item: (_priority_rank(item.priority), item.opened_at, item.id),
        )
        negative_reviews = sorted(
            (
                review
                for review in reviews
                if review.rating <= 2 and _in_period(review.created_at, from_date, to_date)
            ),
            key=lambda item: (item.rating, item.created_at, item.id),
        )
        signals = _build_signals(overview)
        return ProductIssueInvestigation(
            overview=overview,
            relevant_tickets=tickets[:items_limit],
            negative_reviews=negative_reviews[:items_limit],
            signals=signals,
            truncated=InvestigationTruncation(
                tickets=len(tickets) > items_limit,
                reviews=len(negative_reviews) > items_limit,
            ),
        )

    async def find_product_owners(self, product_id: str) -> ProductOwners:
        product = await self._get_product(product_id)
        warnings: list[ContextWarning] = []
        try:
            deliver_edges = await self._graph_api.list_relationships("delivers", to_id=product.id)
        except Exception:
            deliver_edges = []
            warnings.append(_relationship_warning("delivers"))

        project_ids = _unique(edge.from_id for edge in deliver_edges)
        projects, project_warnings = await _fetch_entities(
            project_ids, "project", self._graph_api.get_project
        )
        warnings.extend(project_warnings)

        owner_results, contribution_results = await asyncio.gather(
            asyncio.gather(
                *(self._graph_api.list_relationships("owns", to_id=item) for item in project_ids),
                return_exceptions=True,
            ),
            asyncio.gather(
                *(
                    self._graph_api.list_relationships("contributes-to", to_id=item)
                    for item in project_ids
                ),
                return_exceptions=True,
            ),
        )
        owner_edges = _flatten_relationships(owner_results, "owns", warnings)
        contribution_edges = _flatten_relationships(
            contribution_results, "contributes-to", warnings
        )
        departments, department_warnings = await _fetch_entities(
            _unique(edge.from_id for edge in owner_edges),
            "department",
            self._graph_api.get_department,
        )
        employees, employee_warnings = await _fetch_entities(
            _unique(edge.from_id for edge in contribution_edges),
            "employee",
            self._graph_api.get_employee,
        )
        warnings.extend(department_warnings)
        warnings.extend(employee_warnings)
        employees_by_id = {employee.id: employee for employee in employees}

        contributors: list[Contributor] = []
        for edge in contribution_edges:
            employee = employees_by_id.get(edge.from_id)
            if employee is None:
                continue
            contribution = cast(ContributionEdge, edge)
            contributors.append(
                Contributor(
                    employee=PublicEmployee.from_employee(employee),
                    project_id=edge.to_id,
                    role=contribution.props.role if contribution.props else None,
                    allocation_percent=(
                        contribution.props.allocation_percent if contribution.props else None
                    ),
                )
            )

        return ProductOwners(
            product=product,
            projects=projects,
            departments=departments,
            contributors=contributors,
            warnings=warnings,
        )

    async def _get_product(self, product_id: str) -> Product:
        normalized_id = product_id.strip()
        try:
            return await self._graph_api.get_product(normalized_id)
        except GraphApiNotFoundError as exc:
            raise ProductNotFoundError(normalized_id) from exc


def summarize_overview(result: CommunityOverview) -> str:
    totals = ", ".join(f"{metric.measure}={metric.total:g}" for metric in result.metrics)
    return (
        f"Community overview for {result.product.title} ({result.product.id})\n"
        f"Period: {result.from_date} to {result.to_date}\n"
        f"Metrics: {totals or 'unavailable'}\n"
        f"Tickets: {result.tickets.total} total, {result.tickets.unresolved} unresolved, "
        f"{result.tickets.high_priority} high priority\n"
        f"Reviews: {result.reviews.total} total, average={result.reviews.average_rating}, "
        f"negative={result.reviews.negative}; warnings={len(result.warnings)}"
    )


def summarize_investigation(result: ProductIssueInvestigation) -> str:
    return (
        f"Issue investigation for {result.overview.product.title}\n"
        f"Signals: {'; '.join(result.signals) or 'No notable signals'}\n"
        f"Relevant tickets returned: {len(result.relevant_tickets)}; "
        f"negative reviews returned: {len(result.negative_reviews)}; "
        f"warnings={len(result.overview.warnings)}"
    )


def summarize_owners(result: ProductOwners) -> str:
    return (
        f"Owners for {result.product.title}: {len(result.projects)} projects, "
        f"{len(result.departments)} departments, {len(result.contributors)} contributors; "
        f"warnings={len(result.warnings)}"
    )


async def _fetch_entities[EntityT](
    entity_ids: list[str],
    entity_type: str,
    getter: Callable[[str], Awaitable[EntityT]],
) -> tuple[list[EntityT], list[ContextWarning]]:
    results = await asyncio.gather(
        *(getter(entity_id) for entity_id in entity_ids), return_exceptions=True
    )
    entities: list[EntityT] = []
    warnings: list[ContextWarning] = []
    for entity_id, result in zip(entity_ids, results, strict=True):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, BaseException):
            warnings.append(
                ContextWarning(
                    code="RELATED_ENTITY_UNAVAILABLE",
                    message=f"Could not load related {entity_type}",
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            )
        else:
            entities.append(result)
    return entities, warnings


def _relationship_or_warning(
    result: list[Edge] | BaseException,
    relationship: str,
    warnings: list[ContextWarning],
) -> list[Edge]:
    if isinstance(result, asyncio.CancelledError):
        raise result
    if isinstance(result, BaseException):
        warnings.append(_relationship_warning(relationship))
        return []
    return result


def _flatten_relationships(
    results: Iterable[list[Edge] | BaseException],
    relationship: str,
    warnings: list[ContextWarning],
) -> list[Edge]:
    edges: list[Edge] = []
    for result in results:
        edges.extend(_relationship_or_warning(result, relationship, warnings))
    return edges


def _relationship_warning(relationship: str) -> ContextWarning:
    return ContextWarning(
        code="RELATIONSHIP_UNAVAILABLE",
        message=f"Could not load {relationship} relationships",
        entity_type="relationship",
        entity_id=relationship,
    )


def _metric_series(aggregate: MetricAggregate) -> MetricSeries:
    return MetricSeries(
        measure=aggregate.measure,
        total=aggregate.total,
        points=[
            MetricPoint(day=str(row["key"]), value=float(row["value"])) for row in aggregate.rows
        ],
    )


def _build_signals(overview: CommunityOverview) -> list[str]:
    totals = {metric.measure: metric.total for metric in overview.metrics}
    signals: list[str] = []
    if totals.get("crashes", 0) > 0:
        signals.append(f"{totals['crashes']:g} crashes recorded")
    if totals.get("refunds", 0) > 0:
        signals.append(f"{totals['refunds']:g} refunds recorded")
    if overview.tickets.unresolved:
        signals.append(f"{overview.tickets.unresolved} unresolved tickets")
    if overview.reviews.negative:
        signals.append(f"{overview.reviews.negative} negative reviews")
    return signals


def _validate_period(from_date: date, to_date: date) -> None:
    if from_date > to_date:
        raise InvalidDateRangeError()


def _in_period(value: str, from_date: date, to_date: date) -> bool:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return from_date <= parsed <= to_date


def _priority_rank(priority: str) -> int:
    return {"Urgent": 0, "High": 1, "Normal": 2, "Low": 3}.get(priority, 4)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
