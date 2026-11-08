from agents.base import Agent
from agents.intent_data import Intent
from agents.languages import ASK_GRAMS, ESTIMATE_REPLY, OFFER_VISIT, Language
from services.llm import Message
from tools import ToolContext, ToolResult, run_tool
from tools.calculator_tools import CALCULATOR_TOOLS, ESTIMATE_LOAN, GoldAmount, parse_gold

DEFAULT_CARAT = 22

INSTRUCTIONS = """You give gold loan estimates: grams × purity × today's rate × the \
loan-to-value limit.
- If the facts below hold an estimate, give its range as "about loan_low to loan_high" and \
name one or two interest schemes with their monthly interest.
- Otherwise you need the weight in grams before you can call estimate_loan. If the customer \
did not say it, ask. If they gave pavan, 1 pavan is 8 grams. If they did not say the carat, \
assume 22 carat and say so.
- Always say it is an estimate and that the final amount is decided after valuation at the \
branch.
- Then offer to book a branch visit to value the gold."""


def _gold_in_conversation(text: str, history: list[Message]) -> GoldAmount:
    """Grams and carat from this message; what it leaves out, from earlier customer messages
    ("and if it's 24 carat?" after "I have 30 grams")."""
    found = parse_gold(text)
    grams, carat = found.grams, found.carat
    for message in reversed(history):
        if grams is not None and carat is not None:
            break
        if message.role != "user":
            continue
        earlier = parse_gold(message.text)
        grams = grams if grams is not None else earlier.grams
        carat = carat if carat is not None else earlier.carat
    return GoldAmount(grams, carat)


async def preload(
    context: ToolContext, text: str, history: list[Message]
) -> dict[str, ToolResult] | None:
    """When the weight is in the customer's words, work the estimate out first: one model
    call instead of two. Otherwise the model asks for it, or reads it from words we missed."""
    gold = _gold_in_conversation(text, history)
    if gold.grams is None or gold.grams > 1000:
        return None
    args = {"grams": gold.grams, "carat": gold.carat or DEFAULT_CARAT}
    return {ESTIMATE_LOAN.name: await run_tool(ESTIMATE_LOAN, context, args)}


def _number(grams: float) -> str:
    return f"{grams:g}"


async def fallback(context: ToolContext, text: str, history: list[Message]) -> tuple[str, Language]:
    """The headline demo without any model: the estimate, in the customer's own language.
    The weight can come from earlier in the conversation ("now say it in Malayalam")."""
    language = context.language
    gold = _gold_in_conversation(text, history)
    if gold.grams is None or gold.grams > 1000:
        return ASK_GRAMS[language], language
    carat = gold.carat or DEFAULT_CARAT
    result = await run_tool(ESTIMATE_LOAN, context, {"grams": gold.grams, "carat": carat})
    if "error" in result:
        return ASK_GRAMS[language], language
    reply = ESTIMATE_REPLY[language].format(
        grams=_number(gold.grams), carat=carat, low=result["loan_low"], high=result["loan_high"]
    )
    return f"{reply} {OFFER_VISIT[language]}", language


CALCULATOR_AGENT = Agent(Intent.CALCULATOR, INSTRUCTIONS, CALCULATOR_TOOLS, fallback, preload)
