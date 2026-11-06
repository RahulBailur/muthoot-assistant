from datetime import date, datetime
from typing import Any

from beanie import PydanticObjectId
from pydantic import AwareDatetime

from models.branch import Branch
from models.branch_visit import BranchVisit, VisitPurpose, VisitStatus
from services import visits as booking
from services.scheduling import bookable_slot, open_slots
from time_utils import IST, as_utc, now_utc
from tools import CUSTOMERS_ONLY, Tool, ToolArgs, ToolContext, ToolResult, local_time, schema
from tools.branch_tools import FIND_BRANCHES
from tools.confirmation import confirm_or_propose

MAX_SLOTS_PER_BRANCH = 6


def _describe(visit: BranchVisit, branch: Branch) -> dict[str, Any]:
    when = local_time(visit.slot_start)
    return {
        "visit_id": str(visit.id),
        "branch_name": branch.name,
        "branch_address": f"{branch.address}, {branch.city}",
        "slot_start": as_utc(visit.slot_start).isoformat(),
        "local_time": when,
        "purpose": visit.purpose.value,
        "status": visit.status.value,
        "summary": f"{branch.name} on {when}",
    }


async def _require_open(branch: Branch, slot_start: datetime) -> None:
    """Refuse before asking the customer to confirm something that cannot be done."""
    slot = bookable_slot(branch, slot_start)
    if slot is None:
        raise booking.slot_unavailable()
    booking.check_bookable_day(slot[0].astimezone(IST).date())
    if slot not in await open_slots(branch, slot[0].astimezone(IST).date()):
        raise booking.BookingError(409, "That slot has just been taken")


class FindSlotsArgs(ToolArgs):
    date: date
    branch_id: PydanticObjectId | None = None
    city: str | None = None


async def find_valuation_slots(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    parsed = FindSlotsArgs.model_validate(args)
    if parsed.branch_id is None and not parsed.city:
        return {"error": "Ask the customer which city or branch they want to visit."}
    found = await booking.find_availability(parsed.date, parsed.branch_id, parsed.city)
    if not found:
        return {"error": f"There is no branch in {parsed.city}. Offer find_branches."}
    return {
        "date": parsed.date.isoformat(),
        "branches": [
            {
                "branch_id": str(f.branch.id),
                "branch_name": f.branch.name,
                "open_slots": len(f.slots),
                "first_slots": [
                    {"slot_start": start.isoformat(), "local_time": local_time(start)}
                    for start, _ in f.slots[:MAX_SLOTS_PER_BRANCH]
                ],
            }
            for f in found
        ],
    }


class BookVisitArgs(ToolArgs):
    branch_id: PydanticObjectId
    slot_start: AwareDatetime
    purpose: VisitPurpose = VisitPurpose.NEW_LOAN


async def book_visit(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not context.is_customer:
        return CUSTOMERS_ONLY
    parsed = BookVisitArgs.model_validate(args)
    branch = await booking.get_branch(parsed.branch_id)
    await _require_open(branch, parsed.slot_start)
    summary = f"Book a gold valuation visit at {branch.name} on {local_time(parsed.slot_start)}"
    if proposal := await confirm_or_propose(context, "book_visit", parsed, summary):
        return proposal
    visit, branch = await booking.book(
        context.user, parsed.branch_id, parsed.slot_start, parsed.purpose
    )
    return {"booked": _describe(visit, branch)}


async def list_my_visits(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not context.is_customer:
        return CUSTOMERS_ONLY
    now = now_utc()
    upcoming = [
        _describe(visit, branch)
        for visit, branch in await booking.history(context.user)
        if branch and visit.status == VisitStatus.BOOKED and as_utc(visit.slot_start) > now
    ]
    return {"upcoming": sorted(upcoming, key=lambda v: v["slot_start"])}


class VisitArgs(ToolArgs):
    visit_id: PydanticObjectId


async def cancel_visit(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not context.is_customer:
        return CUSTOMERS_ONLY
    parsed = VisitArgs.model_validate(args)
    current = await BranchVisit.get(parsed.visit_id)
    if current is None or current.customer_id != context.user.id:
        return {"error": "Visit not found."}
    if current.status != VisitStatus.BOOKED:
        return {"error": f"A {current.status} visit cannot be cancelled."}
    branch = await booking.get_branch(current.branch_id)
    summary = f"Cancel the visit to {branch.name} on {local_time(current.slot_start)}"
    if proposal := await confirm_or_propose(context, "cancel_visit", parsed, summary):
        return proposal
    visit, branch = await booking.cancel(context.user, parsed.visit_id)
    return {"cancelled": _describe(visit, branch)}


_SLOT_START = {
    "type": "string",
    "description": (
        "Exact slot_start value returned by find_valuation_slots (ISO 8601 with offset)."
    ),
}

VISIT_TOOLS: tuple[Tool, ...] = (
    FIND_BRANCHES,
    Tool(
        "find_valuation_slots",
        "List open gold valuation slots on one date at one branch, or at every branch in a city.",
        schema(
            {
                "date": {"type": "string", "description": "Date as YYYY-MM-DD."},
                "branch_id": {"type": "string", "description": "branch_id from find_branches."},
                "city": {"type": "string", "description": "City name, if no branch is chosen."},
            },
            ["date"],
        ),
        find_valuation_slots,
    ),
    Tool(
        "book_visit",
        "Book one open valuation slot for the logged-in customer. The first call only proposes it.",
        schema(
            {
                "branch_id": {"type": "string", "description": "branch_id from the slots."},
                "slot_start": _SLOT_START,
                "purpose": {
                    "type": "string",
                    "enum": [p.value for p in VisitPurpose],
                    "description": "Why they are coming. Default new_loan.",
                },
            },
            ["branch_id", "slot_start"],
        ),
        book_visit,
    ),
    Tool(
        "list_my_visits",
        "List the logged-in customer's upcoming branch visits.",
        schema({}),
        list_my_visits,
    ),
    Tool(
        "cancel_visit",
        "Cancel one of the logged-in customer's upcoming visits. The first call only proposes it.",
        schema(
            {"visit_id": {"type": "string", "description": "visit_id from list_my_visits."}},
            ["visit_id"],
        ),
        cancel_visit,
    ),
)
