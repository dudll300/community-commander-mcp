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


class Review(BaseModel):
    id: str
    rating: int
    body: str
    language: str
    created_at: str


class Project(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    started_at: str
    target_date: str


class Department(BaseModel):
    id: str
    name: str


class Edge(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")


class ContributionProperties(BaseModel):
    role: str
    allocation_percent: int


class ContributionEdge(Edge):
    props: ContributionProperties | None = None


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


class MetricPoint(BaseModel):
    day: str
    value: float


class MetricSeries(BaseModel):
    measure: str
    total: float
    points: list[MetricPoint]


class MetricAggregate(BaseModel):
    measure: str
    group_by: str
    total: float
    rows: list[dict[str, str | float]]


class TicketSummary(BaseModel):
    total: int
    unresolved: int
    high_priority: int


class ReviewSummary(BaseModel):
    total: int
    average_rating: float | None
    negative: int


class CommunityOverview(BaseModel):
    product: Product
    from_date: str
    to_date: str
    metrics: list[MetricSeries]
    tickets: TicketSummary
    reviews: ReviewSummary
    warnings: list[ContextWarning]


class InvestigationTruncation(BaseModel):
    tickets: bool = False
    reviews: bool = False


class ProductIssueInvestigation(BaseModel):
    overview: CommunityOverview
    relevant_tickets: list[Ticket]
    negative_reviews: list[Review]
    signals: list[str]
    truncated: InvestigationTruncation


class Contributor(BaseModel):
    employee: PublicEmployee
    project_id: str
    role: str | None = None
    allocation_percent: int | None = None


class ProductOwners(BaseModel):
    product: Product
    projects: list[Project]
    departments: list[Department]
    contributors: list[Contributor]
    warnings: list[ContextWarning]
