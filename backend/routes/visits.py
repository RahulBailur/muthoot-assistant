import secrets
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel, Field

from auth_utils import CurrentUser, CustomerUser, StaffUser, require_role
from models.branch_visit import BranchVisit, VisitPurpose, VisitStatus
from models.user import Role, User
from services import visits as booking
from services.branch_queue import StaffVisitOut, VisitOut, branch_visits, staff_visit_view
from sockets import broadcast_branch
from time_utils import now_utc

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


class WalkInRequest(BaseModel):
    """A customer who came in without booking. Only a name: no phone or account needed."""

    name: str = Field(min_length=2, max_length=80)
    purpose: VisitPurpose = VisitPurpose.NEW_LOAN


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
    """A branch's valuation visits and walk-ins for a day, in time order. Staff see their
    own branch only; an admin chooses one."""
    if user.role == Role.STAFF:
        branch_id = user.branch_id
    if branch_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "branch_id is required")
    return await branch_visits(await booking.get_branch(branch_id), day)


@router.post("/walk-in", status_code=status.HTTP_201_CREATED)
async def walk_in(staff: StaffUser, body: WalkInRequest) -> StaffVisitOut:
    """Add a walk-in to the staff member's own branch queue. They are already at the branch."""
    if staff.branch_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are not assigned to a branch")
    branch = await booking.get_branch(staff.branch_id)
    now = now_utc()
    visit = BranchVisit(
        customer_id=None,
        branch_id=staff.branch_id,
        slot_start=now,
        slot_end=now + timedelta(minutes=branch.slot_minutes),
        purpose=body.purpose,
        status=VisitStatus.ARRIVED,
        arrived_at=now,
        walk_in_name=body.name.strip(),
        # Walk-ins hold no booking slot, so they never clash with one
        slot_key=f"walk-in:{secrets.token_hex(8)}",
    )
    await visit.insert()
    await broadcast_branch(branch, visit)
    return staff_visit_view(visit, branch, None)


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
    await broadcast_branch(branch, visit)
    customer = await User.get(visit.customer_id) if visit.customer_id else None
    return staff_visit_view(visit, branch, customer)
