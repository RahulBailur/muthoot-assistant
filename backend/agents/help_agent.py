import hashlib

from agents.base import Agent
from agents.intent_classifier import normalise
from agents.intent_data import Intent
from agents.languages import Language
from services import gold
from services.llm import Message
from time_utils import today_ist
from tools import ToolContext
from tools.branch_tools import get_gold_rate
from tools.help_tools import FAQ, FAQ_VERSION, HELP_TOOLS, FaqTopic

INSTRUCTIONS = """You answer general questions: documents needed, branch timings and \
locations, today's gold rate, part-payment, interest schemes, renewal and auction notices. \
You also raise complaints and callback requests.
- Use get_faq for the standard answers and say them in your own words, without adding to them.
- raise_ticket changes nothing the first time you call it: it returns needs_confirmation. \
Read back what will be raised and ask for a yes; when the customer agrees, call it again with \
the same arguments. Then give the ticket reference.
- Never say a ticket is raised unless the tool result says ticket_raised.
- If the answer is not in your tools, say you do not have that information and offer a \
callback from the branch."""

# What a question asks for, when the question itself says so. Checked in order.
_TOPIC_WORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "complaint",
        ("complain", "callback", "call back", "call me", "शिकायत", "ದೂರು", "പരാതി", "புகார்"),
    ),
    (
        FaqTopic.DOCUMENTS,
        ("document", "kyc", "proof", "kagaz", "दस्तावेज", "कागज", "ದಾಖಲೆ", "രേഖ", "ஆவண"),
    ),
    (FaqTopic.PART_PAYMENT, ("part payment", "part pay", "partpay", "prepay", "pay early")),
    (
        "gold_rate",
        ("gold rate", "gold price", "rate today", "bhav", "भाव", "ಚಿನ್ನದ ದರ", "സ്വർണവില", "தங்க விலை"),
    ),
    (FaqTopic.INTEREST_SCHEMES, ("scheme", "interest rate")),
    (FaqTopic.TIMINGS, ("timing", "open", "close", "hours", "समय", "ಸಮಯ", "സമയം", "நேரம்")),
]  # fmt: skip

# Topics whose answer is the same for every customer, so a reply may be cached
CACHEABLE = frozenset({FaqTopic.DOCUMENTS, FaqTopic.PART_PAYMENT, "gold_rate", FaqTopic.TIMINGS})


def topic(text: str) -> str | None:
    """What a question asks for, if the question itself says so. None: it needs the
    conversation around it, or it is about something specific (a city, a ticket)."""
    asked = f" {normalise(text)} "
    for name, words in _TOPIC_WORDS:
        if any(word in asked for word in words):
            return str(name)
    return None


async def facts_fingerprint() -> str:
    """Changes whenever the facts a cached answer was written from do: the FAQ text, or
    today's rate (which also changes every day)."""
    rate = await gold.current_rate_24k()
    return hashlib.sha256(f"{FAQ_VERSION}:{today_ist()}:{rate}".encode()).hexdigest()[:16]


async def fallback(context: ToolContext, text: str, history: list[Message]) -> tuple[str, Language]:
    """The rule-based knowledge base."""
    asked_for = topic(text)
    if asked_for == "gold_rate":
        rates = (await get_gold_rate(context, {}))["rate_per_gram"]
        return (
            f"Today's gold rate is {rates['24_carat']} per gram for 24 carat and "
            f"{rates['22_carat']} for 22 carat.",
            "en",
        )
    if asked_for == "complaint":
        return (
            "I can't raise that right now. Please use the Help page to raise a complaint or "
            "ask for a callback, or call your branch.",
            "en",
        )
    if asked_for is not None and asked_for in FaqTopic._value2member_map_:
        return FAQ[FaqTopic(asked_for)], "en"
    return (
        "I can help with documents needed, branch timings, today's gold rate, part-payment "
        "and complaints. What would you like to know?",
        "en",
    )


HELP_AGENT = Agent(Intent.HELP, INSTRUCTIONS, HELP_TOOLS, fallback)
