"""Answers that are the same for every customer, and complaint or callback tickets."""

from enum import StrEnum
from typing import Any

from beanie import PydanticObjectId
from pydantic import Field

from models.ticket import TicketKind
from services import tickets
from tools import CUSTOMERS_ONLY, Tool, ToolArgs, ToolContext, ToolResult, schema
from tools.branch_tools import FIND_BRANCHES, GET_GOLD_RATE
from tools.confirmation import confirm_or_propose


class FaqTopic(StrEnum):
    DOCUMENTS = "documents"
    PART_PAYMENT = "part_payment"
    INTEREST_SCHEMES = "interest_schemes"
    RENEWAL = "renewal"
    AUCTION = "auction"
    TIMINGS = "timings"


# Demo content: replace with the client's own wording before real use.
# Bump FAQ_VERSION when it changes, so cached replies written from the old text are retired.
FAQ_VERSION = "1"
FAQ: dict[FaqTopic, str] = {
    FaqTopic.DOCUMENTS: (
        "Bring your gold jewellery, one photo ID and one address proof (for example Aadhaar, "
        "PAN card, passport, voter ID or driving licence), and a passport-size photo."
    ),
    FaqTopic.PART_PAYMENT: (
        "You can pay part of the loan, or just the interest, at any time at your branch. "
        "Interest is then charged only on what is still owed. There is no charge for paying early."
    ),
    FaqTopic.INTEREST_SCHEMES: (
        "Saver: 12% a year, interest paid every month. Flexi: 14% a year, interest paid every "
        "quarter. Bullet: 18% a year, principal and interest paid together at maturity."
    ),
    FaqTopic.RENEWAL: (
        "Renew before the maturity date by paying the interest due at your branch. The gold "
        "is valued again at that day's rate, and a top-up may be possible."
    ),
    FaqTopic.AUCTION: (
        "If a loan is neither renewed nor closed after maturity, notices are sent before any "
        "auction. Contact your branch early to renew or close the loan and avoid this."
    ),
    FaqTopic.TIMINGS: "Branches are open Monday to Saturday, 9:30 AM to 5:30 PM.",
}


class FaqArgs(ToolArgs):
    topic: FaqTopic


async def get_faq(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    parsed = FaqArgs.model_validate(args)
    return {"topic": parsed.topic.value, "answer": FAQ[parsed.topic]}


class TicketArgs(ToolArgs):
    kind: TicketKind
    message: str = Field(min_length=3, max_length=1000)
    preferred_time: str | None = Field(default=None, max_length=60)
    branch_id: PydanticObjectId | None = None


async def raise_ticket(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not context.is_customer:
        return CUSTOMERS_ONLY
    parsed = TicketArgs.model_validate(args)
    branch = await tickets.ticket_branch(context.user, parsed.branch_id)
    what = "a callback request" if parsed.kind == TicketKind.CALLBACK else "a complaint"
    summary = f"Raise {what} with {branch.name}: {parsed.message}"
    if proposal := await confirm_or_propose(context, "raise_ticket", parsed, summary):
        return proposal
    ticket, branch = await tickets.raise_ticket(
        context.user, parsed.kind, parsed.message, parsed.preferred_time, parsed.branch_id
    )
    return {
        "ticket_raised": {
            "reference": ticket.reference,
            "kind": ticket.kind.value,
            "branch_name": branch.name,
            "summary": f"{ticket.kind.value} {ticket.reference} with {branch.name}",
        }
    }


HELP_TOOLS: tuple[Tool, ...] = (
    Tool(
        "get_faq",
        "The standard answer on documents needed, part-payment, interest schemes, renewal, "
        "auction notices or branch timings.",
        schema(
            {"topic": {"type": "string", "enum": [t.value for t in FaqTopic]}},
            ["topic"],
        ),
        get_faq,
    ),
    GET_GOLD_RATE,
    FIND_BRANCHES,
    Tool(
        "raise_ticket",
        "Raise a complaint or a callback request for the logged-in customer, sent to their "
        "loan's branch unless a branch_id is given. The first call only proposes it.",
        schema(
            {
                "kind": {"type": "string", "enum": [k.value for k in TicketKind]},
                "message": {"type": "string", "description": "What it is about, briefly."},
                "preferred_time": {
                    "type": "string",
                    "description": "For a callback: when to call, if said.",
                },
                "branch_id": {"type": "string", "description": "branch_id from find_branches."},
            },
            ["kind", "message"],
        ),
        raise_ticket,
    ),
)
