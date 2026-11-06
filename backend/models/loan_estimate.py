from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

from time_utils import now_utc


class LoanEstimate(Document):
    """One loan estimate given. A visit booked after it counts as a lead."""

    customer_id: PydanticObjectId | None = None  # None when asked without logging in
    grams: float
    carat: int
    rate_24k_per_gram: int
    low: int  # rupees
    high: int
    created_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = "loan_estimates"
        indexes = [
            IndexModel([("customer_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("created_at", DESCENDING)]),
        ]
