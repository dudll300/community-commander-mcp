from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol, TypeVar

from community_commander.domain.errors import (
    GraphApiNotFoundError,
    InvalidTicketIdError,
    TicketNotFoundError,
)
from community_commander.domain.models import (
    Account,
    Comment,
    ContextWarning,
    Edge,
    Employee,
    Product,
    PublicAccount,
    PublicEmployee,
    Ticket,
    TicketContext,
    Truncation,
)
from community_commander.infrastructure.graph_api import RelationshipName

EntityT = TypeVar("EntityT")


class GraphApi(Protocol):
    async def get_ticket(self, ticket_id: str) -> Ticket: ...

    async def get_product(self, product_id: str) -> Product: ...

    async def get_comment(self, comment_id: str) -> Comment: ...

    async def get_employee(self, employee_id: str) -> Employee: ...

    async def get_account(self, account_id: str) -> Account: ...

    async def list_relationships(
        self,
        relationship: RelationshipName,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
    ) -> list[Edge]: ...


class TicketContextService:
    def __init__(self, graph_api: GraphApi) -> None:
        self._graph_api = graph_api

    async def get_ticket_context(self, ticket_id: str, comments_limit: int) -> TicketContext:
        normalized_id = ticket_id.strip()
        if not normalized_id:
            raise InvalidTicketIdError()
        try:
            ticket = await self._graph_api.get_ticket(normalized_id)
        except GraphApiNotFoundError as exc:
            raise TicketNotFoundError(normalized_id) from exc

        relationship_specs: list[tuple[RelationshipName, str, str]] = [
            ("concerns", "from", normalized_id),
            ("assigned-to", "from", normalized_id),
            ("has-comment", "from", normalized_id),
            ("opened", "to", normalized_id),
        ]
        relationship_results = await asyncio.gather(
            *(
                self._list_relationships(relationship, direction, value)
                for relationship, direction, value in relationship_specs
            ),
            return_exceptions=True,
        )

        warnings: list[ContextWarning] = []
        edges_by_name: dict[RelationshipName, list[Edge]] = {}
        for (relationship, _, _), result in zip(
            relationship_specs, relationship_results, strict=True
        ):
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                warnings.append(
                    ContextWarning(
                        code="RELATIONSHIP_UNAVAILABLE",
                        message=f"Could not load {relationship} relationships",
                        entity_type="relationship",
                        entity_id=relationship,
                    )
                )
                edges_by_name[relationship] = []
            else:
                edges_by_name[relationship] = result

        product_ids = _unique(edge.to_id for edge in edges_by_name["concerns"])
        employee_ids = _unique(edge.to_id for edge in edges_by_name["assigned-to"])
        comment_ids = _unique(edge.to_id for edge in edges_by_name["has-comment"])
        account_ids = _unique(edge.from_id for edge in edges_by_name["opened"])

        products_result, employees_result, accounts_result, comments_result = await asyncio.gather(
            self._fetch_entities(product_ids, "product", self._graph_api.get_product),
            self._fetch_entities(employee_ids, "employee", self._graph_api.get_employee),
            self._fetch_entities(account_ids, "account", self._graph_api.get_account),
            self._fetch_entities(comment_ids, "comment", self._graph_api.get_comment),
        )
        products, product_warnings = products_result
        employees, employee_warnings = employees_result
        accounts, account_warnings = accounts_result
        comments, comment_warnings = comments_result
        warnings.extend(product_warnings)
        warnings.extend(employee_warnings)
        warnings.extend(account_warnings)
        warnings.extend(comment_warnings)

        comments.sort(key=lambda comment: (comment.sequence, comment.created_at, comment.id))
        truncated = len(comment_ids) > comments_limit

        return TicketContext(
            ticket=ticket,
            products=products,
            assignees=[PublicEmployee.from_employee(employee) for employee in employees],
            opened_by=[PublicAccount.from_account(account) for account in accounts],
            comments=comments[:comments_limit],
            warnings=warnings,
            truncated=Truncation(comments=truncated),
        )

    async def _list_relationships(
        self, relationship: RelationshipName, direction: str, value: str
    ) -> list[Edge]:
        if direction == "from":
            return await self._graph_api.list_relationships(relationship, from_id=value)
        return await self._graph_api.list_relationships(relationship, to_id=value)

    async def _fetch_entities(
        self,
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


def summarize_ticket_context(context: TicketContext) -> str:
    product_names = ", ".join(product.title for product in context.products) or "none"
    assignee_names = ", ".join(employee.name for employee in context.assignees) or "unassigned"
    author_names = ", ".join(account.display_name for account in context.opened_by) or "unknown"
    truncation_note = " (truncated)" if context.truncated.comments else ""
    return (
        f"Ticket {context.ticket.id}: {context.ticket.subject}\n"
        f"Status: {context.ticket.status}; priority: {context.ticket.priority}\n"
        f"Products: {product_names}\n"
        f"Assignees: {assignee_names}\n"
        f"Opened by: {author_names}\n"
        f"Comments: {len(context.comments)}{truncation_note}; "
        f"warnings: {len(context.warnings)}"
    )


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
