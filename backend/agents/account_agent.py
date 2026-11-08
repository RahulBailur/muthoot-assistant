from agents.base import Agent
from agents.intent_data import Intent
from agents.languages import Language
from services.llm import Message
from tools import ToolContext, ToolResult, run_tool
from tools.account_tools import ACCOUNT_TOOLS, GET_MY_LOANS, get_my_loans

INSTRUCTIONS = """You tell the logged-in customer about their own gold loans: the amount \
outstanding, interest due and its due date, maturity, renewal and top-up.
- The facts below hold this customer's loans. You can only ever see this customer's loans.
- Name a loan only as "your loan ending" and its four digits.
- If a reminder is listed, say it, most urgent first. An auction warning always comes first.
- A top-up amount is an estimate at today's rate, decided after valuation at the branch.
- To renew, top up or pay, offer to book a branch visit.
- If asked about anyone else's loan, say you can only show the customer their own."""


async def preload(
    context: ToolContext, text: str, history: list[Message]
) -> dict[str, ToolResult] | None:
    """The session customer's own loans. Who that is comes from the session alone."""
    return {GET_MY_LOANS.name: await run_tool(GET_MY_LOANS, context, {})}


async def fallback(context: ToolContext, text: str, history: list[Message]) -> tuple[str, Language]:
    result = await get_my_loans(context, {})
    if "error" in result:
        return "Loan details are only available from a customer account.", "en"
    active = [loan for loan in result["loans"] if loan["status"] == "active"]
    if not active:
        return "You have no active gold loans with us.", "en"
    loan = active[0]
    reply = (
        f"Your loan ending {loan['account_ending']} has {loan['outstanding']} outstanding, "
        f"with interest of {loan['interest_due']} due on {loan['next_due_date']}."
    )
    if loan["reminders"]:
        reply += " " + " ".join(loan["reminders"])
    if len(active) > 1:
        reply += f" You have {len(active) - 1} more active loan(s): see the My loans page."
    return reply, "en"


ACCOUNT_AGENT = Agent(Intent.ACCOUNT, INSTRUCTIONS, ACCOUNT_TOOLS, fallback, preload)
