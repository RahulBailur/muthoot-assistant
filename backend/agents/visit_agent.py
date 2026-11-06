from agents.base import Agent
from agents.intent_data import Intent
from agents.languages import Language
from tools import ToolContext
from tools.visit_tools import VISIT_TOOLS, list_my_visits

INSTRUCTIONS = """You book gold valuation visits at a branch, and cancel them.
- You need a city or branch and a date. Ask for whichever is missing. Use find_branches \
if the customer is unsure which branch.
- Call find_valuation_slots before offering or booking any time. Offer at most three times.
- To cancel, call list_my_visits first to get the visit.
- book_visit and cancel_visit change nothing the first time you call them: they return \
needs_confirmation. Tell the customer what is about to happen and ask for a yes. When the \
customer agrees, call the tool again with the same arguments.
- Never say a visit is booked or cancelled unless the tool result says booked or \
cancelled. Then confirm the branch, date and time.
- A note in square brackets in the conversation records what has already been done or is \
awaiting the customer's yes. Never repeat an action that is already done.
- If a tool returns an error, explain it plainly and offer another option."""


async def fallback(context: ToolContext, text: str) -> tuple[str, Language]:
    if not context.is_customer:
        return "Branch visits can only be booked from a customer account.", "en"
    upcoming = (await list_my_visits(context, {})).get("upcoming", [])
    how = "To book or cancel a visit, please use the Book visit page for now."
    if not upcoming:
        return f"You have no upcoming branch visits. {how}", "en"
    listed = "; ".join(visit["summary"] for visit in upcoming[:3])
    return f"Your upcoming visits: {listed}. {how}", "en"


VISIT_AGENT = Agent(Intent.VISIT, INSTRUCTIONS, VISIT_TOOLS, fallback)
