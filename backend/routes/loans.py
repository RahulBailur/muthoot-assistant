from dataclasses import asdict
from datetime import date

from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from auth_utils import CustomerUser
from models.loan_account import LoanStatus
from services import loans
from services.loans import ReminderKind

router = APIRouter(prefix="/api/loans", tags=["loans"])


class ReminderOut(BaseModel):
    kind: ReminderKind
    message: str
    days: int


class LoanOut(BaseModel):
    """A loan account. The account number is only ever sent masked."""

    id: str
    account_masked: str
    account_last4: str
    branch_id: str
    scheme: str
    principal: int
    outstanding: int
    interest_rate_pa: float
    interest_due: int
    gold_weight_grams: float
    purity_carat: int
    opened_on: date
    next_due_date: date
    maturity_date: date
    status: LoanStatus
    top_up_available: int
    reminders: list[ReminderOut]


@router.get("/me")
async def my_loans(customer: CustomerUser) -> list[LoanOut]:
    """The logged-in customer's own gold loans, with reminders. Customers only: their
    login is the (mock) OTP check that account details need."""
    return [LoanOut(**asdict(view)) for view in await loans.accounts_for(customer)]


@router.get("/{account_id}")
async def loan_detail(customer: CustomerUser, account_id: PydanticObjectId) -> LoanOut:
    view = await loans.account_for(customer, account_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loan account not found")
    return LoanOut(**asdict(view))
