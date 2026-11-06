from datetime import date, datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from time_utils import now_utc


class LoanStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class LoanAccount(Document):
    """A customer's gold loan. Mock data only. Amounts are whole rupees."""

    customer_id: PydanticObjectId
    branch_id: PydanticObjectId
    account_number: str  # 12 digits; never leaves the backend in full
    scheme: str
    principal: int  # amount sanctioned
    outstanding: int  # principal still owed
    interest_rate_pa: float  # percent per year
    interest_due: int  # interest owed by the next due date
    gold_weight_grams: float
    purity_carat: int
    opened_on: date
    next_due_date: date  # next interest payment
    maturity_date: date  # renew or close by then
    status: LoanStatus = LoanStatus.ACTIVE
    created_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = "loan_accounts"
        indexes = [
            IndexModel([("account_number", ASCENDING)], unique=True),
            IndexModel([("customer_id", ASCENDING)]),
        ]
