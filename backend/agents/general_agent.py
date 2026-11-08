from agents.base import Agent
from agents.intent_data import Intent
from agents.languages import CAPABILITIES, Language
from services.llm import Message
from tools import ToolContext

INSTRUCTIONS = """You handle greetings, thanks and anything that is not about loan \
estimates, branch visits, the customer's loan account or general help.
- Be brief and friendly, and say what you can help with: loan estimates, booking a branch \
visit for gold valuation, the customer's loan account, documents, timings, today's gold rate \
and complaints.
- Politely decline anything outside that."""


async def fallback(context: ToolContext, text: str, history: list[Message]) -> tuple[str, Language]:
    return CAPABILITIES[context.language], context.language


GENERAL_AGENT = Agent(Intent.GENERAL, INSTRUCTIONS, (), fallback)
