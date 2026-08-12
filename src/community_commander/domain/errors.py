class CommunityCommanderError(RuntimeError):
    """Base error safe to expose through an MCP tool result."""


class TicketNotFoundError(CommunityCommanderError):
    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"TICKET_NOT_FOUND: ticket '{ticket_id}' was not found")


class InvalidTicketIdError(CommunityCommanderError):
    def __init__(self) -> None:
        super().__init__("INVALID_TICKET_ID: ticket_id must not be blank")


class ProductNotFoundError(CommunityCommanderError):
    def __init__(self, product_id: str) -> None:
        super().__init__(f"PRODUCT_NOT_FOUND: product '{product_id}' was not found")


class InvalidDateRangeError(CommunityCommanderError):
    def __init__(self) -> None:
        super().__init__("INVALID_DATE_RANGE: from_date must not be after to_date")


class GraphApiError(CommunityCommanderError):
    """A sanitized error returned by the upstream graph API adapter."""


class GraphApiNotFoundError(GraphApiError):
    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(f"UPSTREAM_NOT_FOUND: {entity_type} '{entity_id}' was not found")
        self.entity_type = entity_type
        self.entity_id = entity_id


class GraphApiAuthenticationError(GraphApiError):
    def __init__(self) -> None:
        super().__init__("GRAPH_API_AUTH_FAILED: check GRAPH_API_TOKEN")


class GraphApiUnavailableError(GraphApiError):
    def __init__(self) -> None:
        super().__init__("UPSTREAM_UNAVAILABLE: graph API request failed")


class GraphApiResponseError(GraphApiError):
    def __init__(self) -> None:
        super().__init__("UPSTREAM_INVALID_RESPONSE: graph API returned invalid data")
