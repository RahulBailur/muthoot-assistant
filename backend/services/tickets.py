"""Complaint and callback tickets, shared by the HTTP routes and the help agent."""

import secrets

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from models.branch import Branch
from models.loan_account import LoanAccount
from models.ticket import Ticket, TicketKind
from models.user import User
from services.visits import BookingError, get_branch

# No 0/O or 1/I, so a reference read out over the phone is not misheard
REFERENCE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def new_reference() -> str:
    return "GL-" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(6))


async def default_branch_id(customer: User) -> PydanticObjectId | None:
    """The branch of the customer's loan, if they have one."""
    loan = await LoanAccount.find_one(LoanAccount.customer_id == customer.id)
    return loan.branch_id if loan else None


async def ticket_branch(customer: User, branch_id: PydanticObjectId | None) -> Branch:
    """The branch a ticket goes to: the one asked for, else the branch of the customer's loan."""
    branch_id = branch_id or await default_branch_id(customer)
    if branch_id is None:
        raise BookingError(400, "Please choose a branch")
    return await get_branch(branch_id)


async def raise_ticket(
    customer: User,
    kind: TicketKind,
    message: str,
    preferred_time: str | None = None,
    branch_id: PydanticObjectId | None = None,
) -> tuple[Ticket, Branch]:
    branch = await ticket_branch(customer, branch_id)
    if customer.id is None or branch.id is None:
        raise BookingError(400, "Please choose a branch")
    for _ in range(3):  # a clash of random references is rare; try again if it happens
        ticket = Ticket(
            reference=new_reference(),
            customer_id=customer.id,
            branch_id=branch.id,
            kind=kind,
            message=message.strip(),
            preferred_time=preferred_time,
        )
        try:
            await ticket.insert()
        except DuplicateKeyError:
            continue
        return ticket, branch
    raise BookingError(503, "Please try again")
