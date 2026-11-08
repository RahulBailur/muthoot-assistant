"""One text turn: guard the input, route it to a specialist agent, guard the reply, remember it.

Used by the chat endpoint now and by the cascaded voice pipeline later.
"""

import logging
import re
import secrets
from dataclasses import dataclass, field

from agents.account_agent import ACCOUNT_AGENT
from agents.base import Agent, Progress, run_agent
from agents.calculator_agent import CALCULATOR_AGENT
from agents.general_agent import GENERAL_AGENT
from agents.guardrails import check_input, estimate_disclaimer, guard_reply, redact_secrets
from agents.help_agent import CACHEABLE, HELP_AGENT, facts_fingerprint, topic
from agents.intent_classifier import (
    IntentClassifier,
    IntentResult,
    classifier_for_requests,
    keyword_scores,
    normalise,
)
from agents.intent_data import Intent
from agents.languages import Language, requested_language
from agents.visit_agent import VISIT_AGENT
from memory import conversation_memory as memory
from models.user import User
from services.failover import collecting_llm_errors
from services.llm import LLMProvider, LLMUnavailable, Message, get_llm
from services.redis_client import ResponseCache, get_response_cache, reply_key
from tools import ToolContext, track_booking
from tools.confirmation import expire_older_proposals

logger = logging.getLogger(__name__)

AGENTS: dict[Intent, Agent] = {
    agent.intent: agent
    for agent in (VISIT_AGENT, CALCULATOR_AGENT, ACCOUNT_AGENT, HELP_AGENT, GENERAL_AGENT)
}

ROUTER_PROMPT = """Classify the customer's latest message for a gold loan assistant.
Answer with exactly one word from this list:
visit       - book, change or cancel a branch visit or gold valuation slot
calculator  - how much loan they can get for their gold, grams, carat, loan estimate
account     - their own loan: outstanding amount, interest due, due date, renewal, top-up
help        - documents, branch timings or location, gold rate, part-payment, complaints
general     - greetings, thanks, or anything else"""

# A reply that mentions a top-up gives an amount, so it carries the estimate disclaimer too
_TOP_UP = re.compile(r"top ?up|टॉप|ಟಾಪ್|ടോപ്പ്|டாப்", re.IGNORECASE)

# How the turn's intent was decided, most local first
Routing = str  # "keywords" | "embedding" | "llm" | "previous" | "guess" | "guardrail"


@dataclass
class TurnResult:
    reply: str
    intent: Intent
    language: Language  # what the customer wrote or said
    reply_language: Language  # what the reply is in: most rule-based replies are English
    routed_by: Routing
    used_llm: bool
    # The estimate disclaimer, on every reply that gives a loan amount; the UI must show it
    disclaimer: str | None = None
    blocked: bool = False  # a guardrail decided the reply
    guardrail: str | None = None  # which one, e.g. "shares_secret" or "promise"
    tools_called: list[str] = field(default_factory=list)
    cached: bool = False  # answered from the response cache, with no agent run
    # The tier that produced the reply: "cache", a model's name, "rules" or "guardrail"
    answered_by: str = "rules"
    # LLM failures along the way, e.g. ["gemini:429"]: what made a fallback necessary
    llm_errors: list[str] = field(default_factory=list)


async def _cache_key(
    intent: Intent, routed_by: Routing, text: str, language: Language
) -> str | None:
    """The cache key for this turn, or None if its reply must not be shared.

    Shared replies are only those that are the same for everyone (documents, timings, gold
    rate, part-payment), to a question that says what it is asking, routed without the LLM.
    Anything about a customer is never cached.
    """
    if intent != Intent.HELP or routed_by not in ("keywords", "embedding"):
        return None
    if topic(text) not in CACHEABLE:
        return None
    return reply_key(normalise(text), language, await facts_fingerprint())


async def _route(
    local: IntentResult,
    text: str,
    history: list[Message],
    previous: Intent | None,
    llm: LLMProvider,
) -> tuple[Intent, Routing]:
    if not local.needs_llm:
        return local.intent, local.source
    try:
        response = await llm.generate(ROUTER_PROMPT, [*history, Message("user", text)])
        words = response.text.strip().lower().split()
        if words and words[0].strip(".,:") in Intent._value2member_map_:
            return Intent(words[0].strip(".,:")), "llm"
    except LLMUnavailable as error:
        logger.warning("LLM unavailable for routing: %s", error)
    # No LLM verdict. A follow-up with no signal of its own ("and for 24 carat?" is caught by
    # keywords; "what about tomorrow?" is not) stays with the agent that handled the turn
    # before it.
    no_signal = not any(keyword_scores(text).values())
    if no_signal and previous is not None and previous != Intent.GENERAL:
        return previous, "previous"
    return local.intent, "guess"


async def run_text_turn(
    user: User,
    text: str,
    session_id: str,
    llm: LLMProvider | None = None,
    classifier: IntentClassifier | None = None,
    progress: Progress | None = None,
    cache: ResponseCache | None = None,
) -> TurnResult:
    with collecting_llm_errors() as errors:
        result = await _run_text_turn(user, text, session_id, llm, classifier, progress, cache)
    result.llm_errors = errors
    return result


async def _run_text_turn(
    user: User,
    text: str,
    session_id: str,
    llm: LLMProvider | None = None,
    classifier: IntentClassifier | None = None,
    progress: Progress | None = None,
    cache: ResponseCache | None = None,
) -> TurnResult:
    assert user.id is not None  # noqa: S101 — loaded from the database
    llm = llm or get_llm()
    local = (classifier or classifier_for_requests()).classify(text)
    # "Answer in Malayalam": the asked-for language holds for the rest of the conversation,
    # also when the customer types in English, until they ask for another. Writing in one of
    # our Indian languages is the clearest request of all, so that turn is answered in it.
    asked = requested_language(text)
    chosen = asked or await memory.chosen_language(user.id, session_id)
    language = chosen if chosen and (asked or local.language == "en") else local.language
    context = ToolContext(
        user=user,
        language=language,
        session_id=session_id,
        turn_id=secrets.token_hex(8),
    )

    # Input guardrails: before any model or agent sees the turn
    checked = check_input(text, language)
    if checked.risk is not None and checked.reply is not None:
        if progress:
            await progress("routed")
        await expire_older_proposals(context)  # a secret is not a "yes" to anything
        await memory.remember(
            user.id,
            session_id,
            checked.stored_text,
            checked.reply,
            Intent.GENERAL,
            language=chosen,
        )
        return TurnResult(
            reply=checked.reply,
            intent=Intent.GENERAL,
            language=local.language,
            reply_language=language,
            routed_by="guardrail",
            used_llm=False,
            blocked=True,
            guardrail=checked.risk.value,
            answered_by="guardrail",
        )

    history = await memory.recent_messages(user.id, session_id)
    previous = await memory.last_intent(user.id, session_id)
    intent: Intent
    routed_by: Routing
    if asked and previous not in (None, Intent.GENERAL) and not any(keyword_scores(text).values()):
        # Only a language asked for ("say that in Tamil"): the same topic again, in it
        intent, routed_by = previous, "previous"
    else:
        intent, routed_by = await _route(local, text, history, previous, llm)
    if progress:
        await progress("routed")
    if intent == Intent.VISIT:
        await track_booking(context, "received")
        await track_booking(context, "intent_classified")

    cache = cache or get_response_cache()
    key = await _cache_key(intent, routed_by, text, language) if cache.enabled else None
    if key and (hit := await cache.get(key)):
        result = TurnResult(
            reply=hit["reply"],
            intent=intent,
            language=local.language,
            reply_language=hit["reply_language"],
            routed_by=routed_by,
            used_llm=False,
            cached=True,
            answered_by="cache",
        )
        await expire_older_proposals(context)
        await memory.remember(user.id, session_id, text, result.reply, intent, language=chosen)
        return result

    answer = await run_agent(AGENTS[intent], context, text, history, llm, progress)
    await expire_older_proposals(context)

    # Output guardrails: on every reply, whichever agent or model wrote it
    guarded = guard_reply(answer.text, answer.language)
    result = TurnResult(
        reply=guarded.text,
        intent=intent,
        language=local.language,
        reply_language=answer.language,
        routed_by=routed_by,
        used_llm=answer.used_llm or routed_by == "llm",
        blocked=guarded.blocked,
        guardrail=",".join(guarded.violations) or None,
        tools_called=answer.tools_called,
        answered_by=answer.answered_by,
    )
    gives_amount = (
        intent == Intent.CALCULATOR
        or "estimate_loan" in answer.tools_called
        or bool(_TOP_UP.search(result.reply))
    )
    if gives_amount and not guarded.blocked:
        result.disclaimer = estimate_disclaimer(result.reply_language)

    # Only the LLM's wording is worth keeping: a rule-based reply costs nothing to redo
    if key and answer.used_llm and not guarded.blocked:
        await cache.set(key, {"reply": result.reply, "reply_language": result.reply_language})
    await memory.remember(
        user.id,
        session_id,
        redact_secrets(text),
        result.reply,
        intent,
        "; ".join(answer.notes),
        language=chosen,
    )
    return result
