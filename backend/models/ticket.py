from datetime import datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from time_utils import now_utc


class TicketKind(StrEnum):
    COMPLAINT = "complaint"
    CALLBACK = "callback"


class TicketStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class Ticket(Document):
    """A complaint or callback request, routed to the customer's branch."""

    reference: str  # short code the customer can quote, e.g. "GL-7F3K2Q"
    customer_id: PydanticObjectId
    branch_id: PydanticObjectId
    kind: TicketKind
    message: str
    preferred_time: str | None = None  # for a callback, e.g. "after 4 pm"
    status: TicketStatus = TicketStatus.OPEN
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = "tickets"
        indexes = [
            IndexModel([("reference", ASCENDING)], unique=True),
            IndexModel([("branch_id", ASCENDING), ("status", ASCENDING)]),
            IndexModel([("customer_id", ASCENDING)]),
        ]
