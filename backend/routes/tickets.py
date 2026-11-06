from datetime import datetime
from typing import Annotated, Literal

from beanie import PydanticObjectId
from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from auth_utils import CustomerUser, StaffUser, require_role
from models.ticket import Ticket, TicketKind, TicketStatus
from models.user import Role, User
from privacy import mask_phone
from services import tickets
from time_utils import as_utc, now_utc

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

StaffOrAdmin = Annotated[User, Depends(require_role(Role.STAFF, Role.ADMIN))]

STATUS_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED},
    TicketStatus.IN_PROGRESS: {TicketStatus.RESOLVED},
}


class TicketRequest(BaseModel):
    """There is no customer field: the ticket is always for the logged-in customer."""

    kind: TicketKind
    message: str = Field(min_length=3, max_length=1000)
    preferred_time: str | None = Field(default=None, max_length=60)
    # Which branch handles it. Default: the branch of the customer's loan, if they have one.
    branch_id: PydanticObjectId | None = None


class StatusRequest(BaseModel):
    status: Literal[TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]


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


@router.post("", status_code=status.HTTP_201_CREATED)
async def raise_ticket(customer: CustomerUser, body: TicketRequest) -> TicketOut:
    """A complaint or callback request, routed to a branch's staff."""
    ticket, _ = await tickets.raise_ticket(
        customer, body.kind, body.message, body.preferred_time, body.branch_id
    )
    return TicketOut.build(ticket)


@router.get("/me")
async def my_tickets(customer: CustomerUser) -> list[TicketOut]:
    tickets = await Ticket.find(Ticket.customer_id == customer.id).sort("-created_at").to_list()
    return [TicketOut.build(ticket) for ticket in tickets]


@router.get("/branch")
async def branch_tickets(
    user: StaffOrAdmin, branch_id: PydanticObjectId | None = None, include_resolved: bool = False
) -> list[StaffTicketOut]:
    """Complaints and callback requests for a branch, oldest first. Staff see their own
    branch only; an admin chooses one."""
    if user.role == Role.STAFF:
        branch_id = user.branch_id
    if branch_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "branch_id is required")
    query = Ticket.find(Ticket.branch_id == branch_id)
    if not include_resolved:
        query = query.find(Ticket.status != TicketStatus.RESOLVED)
    tickets = await query.sort("+created_at").to_list()
    customers = await User.find(In(User.id, [t.customer_id for t in tickets])).to_list()
    by_id = {customer.id: customer for customer in customers}
    return [_staff_view(ticket, by_id.get(ticket.customer_id)) for ticket in tickets]


@router.put("/{ticket_id}/status")
async def update_status(
    staff: StaffUser, ticket_id: PydanticObjectId, body: StatusRequest
) -> StaffTicketOut:
    ticket = await Ticket.get(ticket_id)
    if ticket is None or ticket.branch_id != staff.branch_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    if body.status not in STATUS_TRANSITIONS.get(ticket.status, set()):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot change status from {ticket.status} to {body.status}"
        )
    ticket.status = TicketStatus(body.status)
    ticket.updated_at = now_utc()
    await ticket.save()
    return _staff_view(ticket, await User.get(ticket.customer_id))


def _staff_view(ticket: Ticket, customer: User | None) -> StaffTicketOut:
    return StaffTicketOut(
        **TicketOut.build(ticket).model_dump(),
        customer_name=customer.name if customer else "Unknown",
        customer_phone_masked=mask_phone(customer.phone) if customer else "",
    )
