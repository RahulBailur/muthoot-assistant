from datetime import datetime
from enum import StrEnum
from typing import Self

from beanie import Document, PydanticObjectId
from pydantic import Field, model_validator
from pymongo import ASCENDING, IndexModel

from time_utils import as_utc, now_utc


class VisitStatus(StrEnum):
    BOOKED = "booked"
    ARRIVED = "arrived"  # at the branch, waiting for valuation
    VALUED = "valued"  # valuation done
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"


class VisitPurpose(StrEnum):
    NEW_LOAN = "new_loan"
    RENEWAL = "renewal"
    TOP_UP = "top_up"
    CLOSE_LOAN = "close_loan"


def slot_key_for(slot_start: datetime) -> str:
    return as_utc(slot_start).strftime("%Y-%m-%dT%H:%MZ")


class BranchVisit(Document):
    """A gold valuation slot booked at a branch, or a walk-in added by branch staff."""

    customer_id: PydanticObjectId | None  # None for a walk-in without an account
    branch_id: PydanticObjectId
    slot_start: datetime  # UTC
    slot_end: datetime  # UTC
    purpose: VisitPurpose = VisitPurpose.NEW_LOAN
    status: VisitStatus = VisitStatus.BOOKED
    # The estimate that led to this visit, if any: what the admin "leads" figure counts
    estimate_id: PydanticObjectId | None = None
    arrived_at: datetime | None = None
    walk_in_name: str | None = None  # set for a walk-in: the name staff typed in
    created_at: datetime = Field(default_factory=now_utc)
    # What the no-double-booking index is built on. It equals the slot start while the
    # visit holds its slot; cancelling rewrites it to a per-visit value, which frees the
    # slot for someone else without deleting the record.
    slot_key: str = ""

    @model_validator(mode="after")
    def _default_slot_key(self) -> Self:
        if not self.slot_key:
            self.slot_key = slot_key_for(self.slot_start)
        return self

    def cancel(self) -> None:
        self.status = VisitStatus.CANCELLED
        self.slot_key = f"cancelled:{self.id}"

    class Settings:
        name = "branch_visits"
        indexes = [
            # No double booking: a second insert for the same branch and slot fails
            IndexModel([("branch_id", ASCENDING), ("slot_key", ASCENDING)], unique=True),
            IndexModel([("branch_id", ASCENDING), ("slot_start", ASCENDING)]),
            IndexModel([("customer_id", ASCENDING), ("slot_start", ASCENDING)]),
        ]
