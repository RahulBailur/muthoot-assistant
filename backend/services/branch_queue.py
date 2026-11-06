"""What branch staff see of their branch today: visits and walk-ins, and open tickets.

Shared by the HTTP routes and the live Socket.IO updates, so both show exactly the same.
Phone numbers are masked here, once, for every screen.
"""

from datetime import date, datetime

from beanie import PydanticObjectId
from beanie.operators import In
from pydantic import BaseModel

from models.branch import Branch
from models.branch_visit import BranchVisit, VisitPurpose, VisitStatus
from models.ticket import Ticket, TicketKind, TicketStatus
from models.user import User
from privacy import mask_phone
from time_utils import as_utc, ist_day_bounds, today_ist


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
    is_walk_in: bool
    arrived_at: datetime | None


class TicketOut(BaseModel):
    id: str
    reference: str
    branch_id: str
    kind: TicketKind
    message: str
    preferred_time: str | None
    status: TicketStatus
    created_at: datetime

    @classmethod
    def build(cls, ticket: Ticket) -> "TicketOut":
        return cls(
            id=str(ticket.id),
            reference=ticket.reference,
            branch_id=str(ticket.branch_id),
            kind=ticket.kind,
            message=ticket.message,
            preferred_time=ticket.preferred_time,
            status=ticket.status,
            created_at=as_utc(ticket.created_at),
        )


class StaffTicketOut(TicketOut):
    customer_name: str
    customer_phone_masked: str  # staff call back through the system, not a copied number


class BranchUpdate(BaseModel):
    """Everything the branch queue screen shows, pushed whenever any of it changes."""

    branch_id: str
    visits: list[StaffVisitOut]
    tickets: list[StaffTicketOut]


def staff_visit_view(visit: BranchVisit, branch: Branch, customer: User | None) -> StaffVisitOut:
    if visit.walk_in_name:
        name, phone = visit.walk_in_name, ""
    else:
        name = customer.name if customer else "Unknown"
        phone = mask_phone(customer.phone) if customer else ""
    return StaffVisitOut(
        **VisitOut.build(visit, branch.name).model_dump(),
        customer_name=name,
        customer_phone_masked=phone,
        is_lead=visit.estimate_id is not None,
        is_walk_in=visit.walk_in_name is not None,
        arrived_at=as_utc(visit.arrived_at) if visit.arrived_at else None,
    )


def staff_ticket_view(ticket: Ticket, customer: User | None) -> StaffTicketOut:
    return StaffTicketOut(
        **TicketOut.build(ticket).model_dump(),
        customer_name=customer.name if customer else "Unknown",
        customer_phone_masked=mask_phone(customer.phone) if customer else "",
    )


async def _users(ids: list[PydanticObjectId | None]) -> dict[PydanticObjectId | None, User]:
    known = [user_id for user_id in ids if user_id is not None]
    return {user.id: user for user in await User.find(In(User.id, known)).to_list()}


async def branch_visits(branch: Branch, day: date | None = None) -> list[StaffVisitOut]:
    """A branch's visits and walk-ins for a day, in time order, cancelled ones left out."""
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
    users = await _users([visit.customer_id for visit in visits])
    return [staff_visit_view(visit, branch, users.get(visit.customer_id)) for visit in visits]


async def branch_tickets(
    branch_id: PydanticObjectId, include_resolved: bool = False
) -> list[StaffTicketOut]:
    """Complaints and callback requests for a branch, oldest first."""
    query = Ticket.find(Ticket.branch_id == branch_id)
    if not include_resolved:
        query = query.find(Ticket.status != TicketStatus.RESOLVED)
    tickets = await query.sort("+created_at").to_list()
    users = await _users([ticket.customer_id for ticket in tickets])
    return [staff_ticket_view(ticket, users.get(ticket.customer_id)) for ticket in tickets]


async def branch_update(branch: Branch) -> BranchUpdate:
    assert branch.id is not None  # noqa: S101 — loaded from the database
    return BranchUpdate(
        branch_id=str(branch.id),
        visits=await branch_visits(branch),
        tickets=await branch_tickets(branch.id),
    )
