"""Branch visit rules, shared by the HTTP routes and (from M2) the branch visit agent.

Every function that acts for a customer takes the `User` it is acting for. That user always
comes from the verified session, so neither a request body nor an LLM can choose it.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from models.branch import Branch
from models.branch_visit import BranchVisit, VisitPurpose, VisitStatus
from models.loan_estimate import LoanEstimate
from models.user import User
from services.scheduling import Slot, bookable_slot, open_slots
from sockets import broadcast_branch
from time_utils import IST, as_utc, now_utc, today_ist

BOOKING_WINDOW_DAYS = 14
HISTORY_DAYS = 90
# An estimate this recent, followed by a booking, makes the visit a lead
LEAD_WINDOW_DAYS = 14


class BookingError(Exception):
    """A request the booking rules refuse. Carries the HTTP status the API answers with."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _slot_taken() -> BookingError:
    return BookingError(409, "That slot has just been taken")


def slot_unavailable() -> BookingError:
    return BookingError(400, "That is not an open valuation slot at this branch")


def _not_found() -> BookingError:
    return BookingError(404, "Visit not found")


@dataclass(frozen=True)
class BranchSlots:
    branch: Branch
    slots: list[Slot]


async def get_branch(branch_id: PydanticObjectId) -> Branch:
    branch = await Branch.get(branch_id)
    if branch is None:
        raise BookingError(404, "Branch not found")
    return branch


def check_bookable_day(day: date) -> None:
    today = today_ist()
    if not today <= day <= today + timedelta(days=BOOKING_WINDOW_DAYS):
        raise BookingError(400, f"Date must be between today and {BOOKING_WINDOW_DAYS} days ahead")


async def find_availability(
    day: date | None = None,
    branch_id: PydanticObjectId | None = None,
    city: str | None = None,
) -> list[BranchSlots]:
    day = day or today_ist()
    check_bookable_day(day)
    if branch_id is not None:
        branches = [await get_branch(branch_id)]
    elif city:
        branches = await branches_in_city(city)
    else:
        branches = await Branch.find_all().to_list()
    return [BranchSlots(branch, await open_slots(branch, day)) for branch in branches]


async def branches_in_city(city: str) -> list[Branch]:
    """Case-insensitive exact city match. The text is escaped, so it cannot act as a regex."""
    pattern = f"^{re.escape(city.strip())}$"
    return await Branch.find({"city": {"$regex": pattern, "$options": "i"}}).to_list()


async def _recent_estimate(customer: User) -> LoanEstimate | None:
    since = now_utc() - timedelta(days=LEAD_WINDOW_DAYS)
    return (
        await LoanEstimate.find(
            LoanEstimate.customer_id == customer.id, LoanEstimate.created_at >= since
        )
        .sort("-created_at")
        .first_or_none()
    )


async def book(
    customer: User,
    branch_id: PydanticObjectId,
    slot_start: datetime,
    purpose: VisitPurpose = VisitPurpose.NEW_LOAN,
) -> tuple[BranchVisit, Branch]:
    branch = await get_branch(branch_id)
    check_bookable_day(as_utc(slot_start).astimezone(IST).date())
    slot = bookable_slot(branch, slot_start)
    if slot is None or customer.id is None or branch.id is None:
        raise slot_unavailable()
    estimate = await _recent_estimate(customer)
    visit = BranchVisit(
        customer_id=customer.id,
        branch_id=branch.id,
        slot_start=slot[0],
        slot_end=slot[1],
        purpose=purpose,
        estimate_id=estimate.id if estimate else None,
    )
    try:
        await visit.insert()
    except DuplicateKeyError:
        raise _slot_taken() from None
    await broadcast_branch(branch, visit)
    return visit, branch


async def cancel(customer: User, visit_id: PydanticObjectId) -> tuple[BranchVisit, Branch]:
    """Only the customer who booked it can cancel, and only while it is still booked."""
    visit = await BranchVisit.get(visit_id)
    if visit is None or visit.customer_id != customer.id:
        raise _not_found()
    if visit.status != VisitStatus.BOOKED:
        raise BookingError(409, f"A {visit.status} visit cannot be cancelled")
    branch = await get_branch(visit.branch_id)
    visit.cancel()
    await visit.save()
    await broadcast_branch(branch, visit)
    return visit, branch


async def history(customer: User) -> list[tuple[BranchVisit, Branch | None]]:
    """The customer's own visits with their branch: the last 90 days plus upcoming."""
    since = now_utc() - timedelta(days=HISTORY_DAYS)
    visits = (
        await BranchVisit.find(
            BranchVisit.customer_id == customer.id, BranchVisit.slot_start >= since
        )
        .sort("-slot_start")
        .to_list()
    )
    branches = {branch.id: branch for branch in await Branch.find_all().to_list()}
    return [(visit, branches.get(visit.branch_id)) for visit in visits]
