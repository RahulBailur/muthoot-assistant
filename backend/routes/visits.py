from datetime import date, datetime
from typing import Annotated, Literal

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel

from auth_utils import CurrentUser, CustomerUser, StaffUser, require_role
from models.branch import Branch
from models.branch_visit import BranchVisit, VisitPurpose, VisitStatus
from models.user import Role, User
from privacy import mask_phone
from services import visits as booking
from time_utils import as_utc, ist_day_bounds, now_utc, today_ist

router = APIRouter(prefix="/api/visits", tags=["visits"])

StaffOrAdmin = Annotated[User, Depends(require_role(Role.STAFF, Role.ADMIN))]

# What branch staff may move a visit to, from each state
STATUS_TRANSITIONS: dict[VisitStatus, set[VisitStatus]] = {
    VisitStatus.BOOKED: {VisitStatus.ARRIVED, VisitStatus.NO_SHOW},
    VisitStatus.ARRIVED: {VisitStatus.VALUED},
}


class SlotOut(BaseModel):
    start: datetime
    end: datetime


class BranchAvailability(BaseModel):
    branch_id: str
    branch_name: str
    city: str
    slots: list[SlotOut]


class BookRequest(BaseModel):
    """There is no customer field: the visit is always for the logged-in customer."""

    branch_id: PydanticObjectId
    slot_start: AwareDatetime
    purpose: VisitPurpose = VisitPurpose.NEW_LOAN


class StatusRequest(BaseModel):
    status: Literal[VisitStatus.ARRIVED, VisitStatus.VALUED, VisitStatus.NO_SHOW]


class VisitOut(BaseModel):
    id: str
    branch_id: str
    branch_name: str
    slot_start: datetime
    slot_end: datetime
    purpose: VisitPurpose
    status: VisitStatus

    @classmethod
    def build(cls, visit: BranchVisit, branch_name: str) -> "VisitOut":
        return cls(
            id=str(visit.id),
            branch_id=str(visit.branch_id),
            branch_name=branch_name,
            slot_start=as_utc(visit.slot_start),
            slot_end=as_utc(visit.slot_end),
            purpose=visit.purpose,
            status=visit.status,
        )


class StaffVisitOut(VisitOut):
    """What branch staff see: who is coming, with the phone masked."""

    customer_name: str
    customer_phone_masked: str
    is_lead: bool  # booked after a loan estimate
    arrived_at: datetime | None


@router.get("/availability")
async def availability(
    user: CurrentUser,
    day: Annotated[date | None, Query(alias="date")] = None,
    branch_id: PydanticObjectId | None = None,
    city: str | None = None,
) -> list[BranchAvailability]:
    return [
        BranchAvailability(
            branch_id=str(found.branch.id),
            branch_name=found.branch.name,
            city=found.branch.city,
            slots=[SlotOut(start=start, end=end) for start, end in found.slots],
        )
        for found in await booking.find_availability(day, branch_id, city)
    ]


@router.post("/book", status_code=status.HTTP_201_CREATED)
async def book(customer: CustomerUser, body: BookRequest) -> VisitOut:
    visit, branch = await booking.book(customer, body.branch_id, body.slot_start, body.purpose)
    return VisitOut.build(visit, branch.name)


@router.get("/me")
async def my_visits(customer: CustomerUser) -> list[VisitOut]:
    """The logged-in customer's own visits: the last 90 days plus anything upcoming."""
    return [
        VisitOut.build(visit, branch.name if branch else "Unknown")
        for visit, branch in await booking.history(customer)
    ]


@router.post("/{visit_id}/cancel")
async def cancel(customer: CustomerUser, visit_id: PydanticObjectId) -> VisitOut:
    visit, branch = await booking.cancel(customer, visit_id)
    return VisitOut.build(visit, branch.name)


@router.get("/branch")
async def branch_day(
    user: StaffOrAdmin,
    day: Annotated[date | None, Query(alias="date")] = None,
    branch_id: PydanticObjectId | None = None,
) -> list[StaffVisitOut]:
    """A branch's valuation appointments for a day, in slot order. Staff see their own
    branch only; an admin chooses one."""
    if user.role == Role.STAFF:
        branch_id = user.branch_id
    if branch_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "branch_id is required")
    branch = await booking.get_branch(branch_id)
    day_start, day_end = ist_day_bounds(day or today_ist())
    visits = (
        await BranchVisit.find(
            BranchVisit.branch_id == branch.id,
            BranchVisit.slot_start >= day_start,
            BranchVisit.slot_start < day_end,
            BranchVisit.status != VisitStatus.CANCELLED,
        )
        .sort("+slot_start")
        .to_list()
    )
    customers = await User.find(In(User.id, [v.customer_id for v in visits])).to_list()
    by_id = {customer.id: customer for customer in customers}
    return [_staff_view(visit, branch, by_id.get(visit.customer_id)) for visit in visits]


@router.put("/{visit_id}/status")
async def update_status(
    staff: StaffUser, visit_id: PydanticObjectId, body: StatusRequest
) -> StaffVisitOut:
    """The "customer arrived" button, and marking the valuation done or a no-show.
    Only for visits at the staff member's own branch."""
    visit = await BranchVisit.get(visit_id)
    if visit is None or visit.branch_id != staff.branch_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Visit not found")
    if body.status not in STATUS_TRANSITIONS.get(visit.status, set()):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot change status from {visit.status} to {body.status}"
        )
    visit.status = VisitStatus(body.status)
    if visit.status == VisitStatus.ARRIVED:
        visit.arrived_at = now_utc()
    await visit.save()
    branch = await booking.get_branch(visit.branch_id)
    return _staff_view(visit, branch, await User.get(visit.customer_id))


def _staff_view(visit: BranchVisit, branch: Branch, customer: User | None) -> StaffVisitOut:
    return StaffVisitOut(
        **VisitOut.build(visit, branch.name).model_dump(),
        customer_name=customer.name if customer else "Unknown",
        customer_phone_masked=mask_phone(customer.phone) if customer else "",
        is_lead=visit.estimate_id is not None,
        arrived_at=as_utc(visit.arrived_at) if visit.arrived_at else None,
    )
