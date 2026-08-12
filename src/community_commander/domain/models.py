from __future__ import annotations

from pydantic import BaseModel, Field


class Ticket(BaseModel):
    id: str
    subject: str
    category: str
    status: str
    priority: str
    opened_at: str
    resolved_at: str | None = None


class Product(BaseModel):
    id: str
    title: str
    kind: str
    genre: str
    platform: str
    status: str
    price_usd: float
    released_at: str


class Comment(BaseModel):
    id: str
    body: str
    author_kind: str
    sequence: int
    created_at: str


class Employee(BaseModel):
    id: str
    name: str
    email: str
    title: str
    grade: str
    location: str
    hired_at: str
    fte: float


class Account(BaseModel):
    id: str
    email: str
    display_name: str
    country: str
    status: str
    created_at: str


class Edge(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")


class RelationshipPage(BaseModel):
    count: int
    limit: int
    offset: int
    items: list[Edge]
    next_cursor: str | None = None


class PublicEmployee(BaseModel):
    id: str
    name: str
    title: str
    grade: str
    location: str

    @classmethod
    def from_employee(cls, employee: Employee) -> PublicEmployee:
        return cls(**employee.model_dump(include={"id", "name", "title", "grade", "location"}))


class PublicAccount(BaseModel):
    id: str
    display_name: str
    country: str
    status: str

    @classmethod
    def from_account(cls, account: Account) -> PublicAccount:
        return cls(**account.model_dump(include={"id", "display_name", "country", "status"}))


class ContextWarning(BaseModel):
    code: str
    message: str
    entity_type: str
    entity_id: str


class Truncation(BaseModel):
    comments: bool = False


class TicketContext(BaseModel):
    ticket: Ticket
    products: list[Product]
    assignees: list[PublicEmployee]
    opened_by: list[PublicAccount]
    comments: list[Comment]
    warnings: list[ContextWarning]
    truncated: Truncation
