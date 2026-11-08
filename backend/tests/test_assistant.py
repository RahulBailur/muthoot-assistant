"""The assistant end to end, through `run_text_turn`, with a scripted model or none at all."""

from typing import Any

import fakeredis.aioredis
import pytest
from httpx import AsyncClient

from agents.languages import (
    ASK_GRAMS,
    CAPABILITIES,
    ESTIMATE_DISCLAIMER,
    INVESTMENT_REFUSAL,
    SAFE_FALLBACK,
    SECRET_WARNING,
)
from agents.orchestrator import run_text_turn
from models.branch_visit import BranchVisit
from models.conversation_turn import ConversationTurn
from models.gold_rate import GoldRate
from models.loan_estimate import LoanEstimate
from models.pending_action import PendingAction
from models.user import Role, User
from services.failover import CircuitBreaker, FailoverLLM
from services.llm import LLMUnavailable, MockLLM
from services.redis_client import ResponseCache
from tests.helpers import make_branch, make_loan, make_user, slot
from tests.llm_helpers import ScriptedLLM
from time_utils import today_ist

SESSION = "session-0001"


async def turn(user: User, text: str, llm: Any = None, cache: Any = None, session: str = SESSION):  # type: ignore[no-untyped-def]
    return await run_text_turn(user, text, session, llm=llm or MockLLM(), cache=cache)


# --- the headline demo, with no model at all ---


async def test_headline_hindi_estimate_works_without_any_model(client: AsyncClient) -> None:
    customer = await make_user()

    result = await turn(customer, "Mere paas 30 gram sona hai, kitna loan milega?")

    assert result.intent == "calculator"
    assert result.language == result.reply_language == "hi"
    # 30 g × 22/24 × ₹12,000 × 75% = ₹2,47,500, and 10% lower for the low end
    assert "₹2,22,700" in result.reply and "₹2,47,500" in result.reply
    assert "लोन" in result.reply
    assert result.disclaimer == ESTIMATE_DISCLAIMER["hi"]
    assert result.answered_by == "rules"
    estimate = await LoanEstimate.find_one()
    assert estimate is not None and estimate.customer_id == customer.id


async def test_malayalam_estimate_in_pavan(client: AsyncClient) -> None:
    customer = await make_user()

    result = await turn(customer, "എന്റെ കയ്യിൽ 4 പവൻ സ്വർണമുണ്ട്, എത്ര വായ്പ കിട്ടും?")

    # 4 pavan = 32 g of 22 carat: ₹2,64,000 at 75%
    assert result.reply_language == "ml"
    assert "₹2,37,600" in result.reply and "₹2,64,000" in result.reply
    assert result.disclaimer == ESTIMATE_DISCLAIMER["ml"]


async def test_estimate_without_a_weight_asks_for_one(client: AsyncClient) -> None:
    result = await turn(await make_user(), "How much loan can I get on my gold?")

    assert result.reply == ASK_GRAMS["en"]
    assert await LoanEstimate.count() == 0


# --- input guardrails ---


@pytest.mark.guardrail
@pytest.mark.parametrize(
    ("text", "language"),
    [("my otp is 482913", "en"), ("मेरा ओटीपी 482913 है", "hi"), ("என் ஓடிபி 482913", "ta")],
)
async def test_a_shared_otp_gets_the_warning_and_is_never_stored(
    client: AsyncClient, text: str, language: str
) -> None:
    customer = await make_user()
    llm = ScriptedLLM(script=["anything"])

    result = await turn(customer, text, llm)

    assert result.reply == SECRET_WARNING[language]  # type: ignore[index]
    assert result.blocked and result.guardrail == "shares_secret"
    assert llm.calls == []  # the model never saw it
    stored = await ConversationTurn.find_all().to_list()
    assert stored and all("482913" not in t.text for t in stored)


@pytest.mark.guardrail
async def test_investment_question_is_refused_before_the_model(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=["Yes, buy now, prices will rise!"])

    result = await turn(await make_user(), "Should I buy gold now?", llm)

    assert result.reply == INVESTMENT_REFUSAL["en"]
    assert result.guardrail == "investment_question"
    assert llm.calls == []


# --- output guardrails, on what a model actually wrote ---


@pytest.mark.guardrail
async def test_model_asking_for_an_otp_is_replaced(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=["Sure! Please share your OTP so I can verify you."])

    result = await turn(await make_user(), "hello", llm)

    assert result.reply == SAFE_FALLBACK["en"]
    assert result.blocked and result.guardrail == "asks_for_secret"


@pytest.mark.guardrail
async def test_model_promising_approval_is_replaced(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=["Great news, your loan is approved for ₹2,47,500!"])

    result = await turn(await make_user(), "I have 30 grams of 22 carat gold", llm)

    assert result.reply == SAFE_FALLBACK["en"]
    assert result.guardrail == "promise"
    assert result.disclaimer is None


@pytest.mark.guardrail
async def test_model_reply_has_numbers_masked(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=["We will call you back on 9876543210."], route="help")

    result = await turn(await make_user(), "please arrange it", llm)

    assert "9876543210" not in result.reply
    assert "XXXXXX3210" in result.reply


# --- calculator agent ---


async def test_estimate_is_worked_out_before_the_model_is_asked(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=["About ₹2,22,700 to ₹2,47,500. It is an estimate."])

    result = await turn(await make_user(), "I have 30 grams of 22 carat gold, how much loan?", llm)

    assert result.answered_by == "scripted"
    assert result.tools_called == ["estimate_loan"]
    [call] = llm.calls  # one model call, with the facts in hand and no tools to call
    assert call.tools == []
    assert "₹2,47,500" in call.system


async def test_follow_up_carat_reuses_the_weight_from_earlier(client: AsyncClient) -> None:
    customer = await make_user()
    llm = ScriptedLLM(script=["first answer", "second answer"])

    await turn(customer, "I have 30 grams of gold", llm)
    await turn(customer, "and if it is 24 carat?", llm)

    # 30 g of 24 carat at ₹12,000 × 75% = ₹2,70,000
    assert "₹2,70,000" in llm.calls[-1].system


async def test_model_asks_when_it_must_choose_the_tool(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=[[("estimate_loan", {"grams": 16, "carat": 22})], "about that"])

    result = await turn(await make_user(), "how much loan for two bangles of 8 gm each?", llm)

    assert result.answered_by == "scripted"
    assert llm.last_tool_result("estimate_loan") is not None


# --- account agent ---


@pytest.mark.guardrail
async def test_account_reply_names_only_the_last_four_digits(client: AsyncClient) -> None:
    customer = await make_user()
    loan = await make_loan(customer, await make_branch())

    result = await turn(customer, "What is my outstanding amount?")

    assert f"ending {loan.account_number[-4:]}" in result.reply
    assert loan.account_number not in result.reply
    assert "₹1,00,000" in result.reply


@pytest.mark.guardrail
async def test_the_model_is_only_ever_given_the_last_four_digits(client: AsyncClient) -> None:
    customer = await make_user()
    loan = await make_loan(customer, await make_branch())
    llm = ScriptedLLM(script=["Your loan is fine."])

    await turn(customer, "What is my outstanding amount?", llm)

    assert loan.account_number not in llm.calls[0].system
    assert customer.phone not in llm.calls[0].system


@pytest.mark.guardrail
async def test_staff_get_no_account_details(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    await make_loan(await make_user(), branch)

    result = await turn(staff, "What is my outstanding amount?")

    assert "customer account" in result.reply


# --- visit agent: two-step confirmation ---


def _book_args(branch_id: str, **extra: Any) -> dict[str, Any]:
    return {"branch_id": branch_id, "slot_start": slot(1).isoformat(), **extra}


async def test_booking_needs_a_yes_in_the_next_turn(client: AsyncClient) -> None:
    customer = await make_user()
    branch = await make_branch()
    args = _book_args(str(branch.id))
    llm = ScriptedLLM(
        script=[[("book_visit", args)], "Shall I book it?", [("book_visit", args)], "Booked."],
        route="visit",
    )

    await turn(customer, "Book a valuation visit at the Kochi branch tomorrow", llm)
    assert await BranchVisit.count() == 0
    assert llm.last_tool_result("book_visit")["needs_confirmation"]  # type: ignore[index]

    result = await turn(customer, "yes please", llm)

    assert result.intent == "visit"
    visit = await BranchVisit.find_one()
    assert visit is not None and visit.customer_id == customer.id


@pytest.mark.guardrail
async def test_the_model_cannot_confirm_its_own_proposal_in_one_turn(client: AsyncClient) -> None:
    branch = await make_branch()
    args = _book_args(str(branch.id))
    llm = ScriptedLLM(script=[[("book_visit", args)], [("book_visit", args)], "Booked!"])

    await turn(await make_user(), "Book a valuation visit tomorrow", llm)

    assert await BranchVisit.count() == 0


@pytest.mark.guardrail
async def test_a_customer_id_from_the_model_is_ignored(client: AsyncClient) -> None:
    customer, someone_else = await make_user(), await make_user()
    branch = await make_branch()
    args = _book_args(str(branch.id), customer_id=str(someone_else.id))
    llm = ScriptedLLM(script=[[("book_visit", args)], "ok?", [("book_visit", args)], "done"])
    llm.route = "visit"

    await turn(customer, "Book a visit tomorrow", llm)
    await turn(customer, "yes", llm)

    visit = await BranchVisit.find_one()
    assert visit is not None and visit.customer_id == customer.id


async def test_a_proposal_is_withdrawn_when_the_model_fails(client: AsyncClient) -> None:
    branch = await make_branch()
    llm = ScriptedLLM(script=[[("book_visit", _book_args(str(branch.id)))], LLMUnavailable("x")])

    result = await turn(await make_user(), "Book a visit tomorrow", llm)

    assert result.answered_by == "rules"
    assert await PendingAction.count() == 0


async def test_a_tool_outside_the_agents_set_is_refused(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=[[("get_my_loans", {})], "sorry"])

    await turn(await make_user(), "What documents do I need?", llm)

    assert "not available" in llm.last_tool_result("get_my_loans")["error"]  # type: ignore[index]


async def test_a_visit_booked_after_an_estimate_is_a_lead(client: AsyncClient) -> None:
    customer = await make_user()
    branch = await make_branch()
    args = _book_args(str(branch.id))
    llm = ScriptedLLM(
        script=["estimate", [("book_visit", args)], "ok?", [("book_visit", args)], "done"],
        route="visit",
    )

    await turn(customer, "I have 30 grams of 22 carat gold", llm)
    await turn(customer, "Book a visit tomorrow", llm)
    await turn(customer, "yes", llm)

    visit = await BranchVisit.find_one()
    assert visit is not None and visit.estimate_id is not None


# --- help agent and the response cache ---


async def test_help_answers_from_the_faq_without_a_model(client: AsyncClient) -> None:
    result = await turn(await make_user(), "What documents do I need?")

    assert "photo ID" in result.reply


async def test_gold_rate_without_a_model(client: AsyncClient) -> None:
    result = await turn(await make_user(), "What is the gold rate today?")

    assert "₹12,000" in result.reply and "₹11,000" in result.reply


async def test_greeting_in_tamil_lists_what_the_assistant_does(client: AsyncClient) -> None:
    result = await turn(await make_user(), "வணக்கம்")

    assert result.reply == CAPABILITIES["ta"]


def _cache() -> ResponseCache:
    return ResponseCache(fakeredis.aioredis.FakeRedis(decode_responses=True), 60)


async def test_same_question_is_answered_from_the_cache(client: AsyncClient) -> None:
    cache = _cache()
    first_llm = ScriptedLLM(script=["Bring a photo ID and address proof."])

    first = await turn(await make_user(), "What documents do I need?", first_llm, cache)
    second = await turn(await make_user(), "What documents do I need?", ScriptedLLM(), cache)

    assert first.answered_by == "scripted"
    assert second.cached and second.answered_by == "cache"
    assert second.reply == first.reply


async def test_a_new_gold_rate_retires_cached_rate_answers(client: AsyncClient) -> None:
    cache = _cache()
    await turn(await make_user(), "gold rate today?", ScriptedLLM(script=["₹12,000"]), cache)
    await GoldRate(day=today_ist().isoformat(), rate_24k_per_gram=13000).insert()

    again = await turn(
        await make_user(), "gold rate today?", ScriptedLLM(script=["₹13,000"]), cache
    )

    assert not again.cached
    assert again.reply == "₹13,000"


async def test_answers_about_a_customer_are_never_cached(client: AsyncClient) -> None:
    cache = _cache()
    customer = await make_user()
    await make_loan(customer, await make_branch())

    await turn(customer, "What is my outstanding?", ScriptedLLM(script=["₹1,00,000"]), cache)
    again = await turn(customer, "What is my outstanding?", ScriptedLLM(script=["x"]), cache)

    assert not again.cached


# --- failover ---


async def test_failover_moves_to_the_next_tier_and_records_why(client: AsyncClient) -> None:
    down = ScriptedLLM(script=[LLMUnavailable("Gemini returned HTTP 429")], name="gemini")
    local = ScriptedLLM(script=["Hello from the local model."], name="ollama")
    llm = FailoverLLM([(down, CircuitBreaker(3, 60)), (local, CircuitBreaker(3, 60))])

    result = await turn(await make_user(), "hello", llm)

    assert result.answered_by == "ollama"
    assert result.llm_errors == ["gemini:429"]


async def test_an_open_circuit_skips_the_provider(client: AsyncClient) -> None:
    down = ScriptedLLM(script=[LLMUnavailable("timeout")] * 3, name="gemini")
    breaker = CircuitBreaker(threshold=1, cooldown_s=60)
    llm = FailoverLLM([(down, breaker)])

    await turn(await make_user(), "hello", llm)
    result = await turn(await make_user(), "hello", llm)

    assert breaker.state == "open"
    assert "gemini:circuit_open" in result.llm_errors
    assert result.answered_by == "rules"


# --- asking for a language ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Can you answer this in Malayalam? The same sentences you just repeated.", "ml"),
        ("Tamil mein batao", "ta"),
        ("മലയാളത്തിൽ പറയൂ", "ml"),
        ("मुझे हिंदी में बताओ", "hi"),
        ("please reply in Kannada", "kn"),
        ("answer in English please", "en"),
        ("Do you have a branch in Tamil Nadu?", None),  # a place, not a request
        ("I speak Hindi and Tamil", None),  # two languages: no single choice
        ("kannada", None),  # a bare name in Latin script is not a request
        ("What is my outstanding amount?", None),
    ],
)
def test_a_request_for_a_language_is_recognised(text: str, language: str | None) -> None:
    from agents.languages import requested_language

    assert requested_language(text) == language


async def test_say_that_again_in_malayalam_repeats_the_estimate_in_it(client: AsyncClient) -> None:
    """What the demo recording showed: the follow-up got an English "how many grams?"."""
    customer = await make_user()
    await turn(customer, "Mere paas 30 gram sona hai, kitna loan milega?")

    result = await turn(
        customer, "Can you answer this in Malayalam? The same sentences you just repeated."
    )

    assert result.intent == "calculator" and result.routed_by == "previous"
    assert result.reply_language == "ml"
    assert "₹2,22,700" in result.reply and "വായ്പ" in result.reply
    assert result.disclaimer == ESTIMATE_DISCLAIMER["ml"]


async def test_the_chosen_language_holds_until_another_is_asked_for(client: AsyncClient) -> None:
    customer = await make_user()
    await turn(customer, "Tamil mein batao")

    in_english = await turn(customer, "hello")
    back = await turn(customer, "answer in English please")
    after = await turn(customer, "hello")

    assert in_english.reply == CAPABILITIES["ta"]
    assert back.reply_language == "en"
    assert after.reply == CAPABILITIES["en"]


async def test_writing_in_another_indian_language_answers_in_that_one(client: AsyncClient) -> None:
    customer = await make_user()
    await turn(customer, "please reply in Malayalam")

    result = await turn(customer, "मेरे पास 30 ग्राम सोना है, कितना लोन मिलेगा?")

    assert result.reply_language == "hi"


async def test_the_model_is_told_the_chosen_language(client: AsyncClient) -> None:
    customer = await make_user()
    llm = ScriptedLLM(script=["சரி", "உங்கள் நிலுவை ₹1,00,000"])
    await make_loan(customer, await make_branch())

    await turn(customer, "Tamil mein batao", llm)
    await turn(customer, "What is my outstanding amount?", llm)

    assert "Reply in Tamil." in llm.calls[-1].system
