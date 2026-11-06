"""Financial safety guardrails. Marked `guardrail`: CI runs them as their own required job."""

import pytest

from agents.guardrails import (
    InputRisk,
    Violation,
    asks_investment_advice,
    check_input,
    find_violations,
    guard_reply,
    mask_long_numbers,
    redact_secrets,
    shares_secret,
)
from agents.languages import (
    ASK_GRAMS,
    CAPABILITIES,
    ESTIMATE_DISCLAIMER,
    ESTIMATE_REPLY,
    INVESTMENT_REFUSAL,
    LANGUAGES,
    OFFER_VISIT,
    SAFE_FALLBACK,
    SECRET_WARNING,
)

pytestmark = pytest.mark.guardrail


# --- every language has every reply that is said without a model ---


@pytest.mark.parametrize(
    "table",
    [
        SECRET_WARNING,
        INVESTMENT_REFUSAL,
        ESTIMATE_DISCLAIMER,
        SAFE_FALLBACK,
        CAPABILITIES,
        ESTIMATE_REPLY,
        ASK_GRAMS,
        OFFER_VISIT,
    ],
)
def test_every_language_has_the_fixed_replies(table: dict[str, str]) -> None:
    assert set(table) == set(LANGUAGES)
    assert all(text.strip() for text in table.values())


def test_the_secret_warning_names_muthoot_and_the_otp() -> None:
    assert "Muthoot will never ask for your OTP" in SECRET_WARNING["en"]
    assert all("OTP" in text for text in SECRET_WARNING.values())


# --- input: sharing a secret ---


@pytest.mark.parametrize(
    "text",
    [
        "my otp is 482913",
        "OTP: 4829 13",
        "here is the pin 1234",
        "cvv 123",
        "my password is tiger123",
        "mera otp 482913 hai",
        "मेरा ओटीपी 482913 है",
        "ನನ್ನ ಒಟಿಪಿ 482913",
        "എന്റെ ഒടിപി 482913 ആണ്",
        "என் ஓடிபி 482913",
    ],
)
def test_sharing_a_secret_is_caught(text: str) -> None:
    assert shares_secret(text)


@pytest.mark.parametrize(
    "text",
    [
        "I have 30 grams of gold",
        "find a branch near pin code 682011",
        "branch for pincode 560041",
        "I didn't get an OTP",  # no digits: a question, not a secret
        "what is my loan outstanding",
    ],
)
def test_ordinary_messages_are_not_secrets(text: str) -> None:
    assert not shares_secret(text)


def test_secret_digits_are_redacted_but_grams_are_not() -> None:
    assert "482913" not in redact_secrets("my otp is 482913")
    assert "tiger123" not in redact_secrets("my password is tiger123")
    assert redact_secrets("I have 30 grams") == "I have 30 grams"


@pytest.mark.parametrize("language", LANGUAGES)
def test_input_check_answers_a_secret_with_the_warning(language: str) -> None:
    checked = check_input("otp 482913", language)  # type: ignore[arg-type]

    assert checked.risk == InputRisk.SHARES_SECRET
    assert checked.reply == SECRET_WARNING[language]  # type: ignore[index]
    assert "482913" not in checked.stored_text


# --- input: investment questions ---


@pytest.mark.parametrize(
    "text",
    [
        "should I buy gold now?",
        "Should I sell my gold this month",
        "is it a good time to invest",
        "will the gold price go up next year",
        "gold price will rise?",
        "sona khareedna chahiye kya",
        "क्या अभी सोना खरीद लूं",
        "ಚಿನ್ನ ಖರೀದಿಸಬೇಕೇ",
        "ഇപ്പോൾ സ്വർണം വാങ്ങണോ",
        "இப்போது தங்கம் வாங்கலாமா",
    ],
)
def test_investment_questions_are_caught(text: str) -> None:
    assert asks_investment_advice(text)
    assert check_input(text, "en").risk == InputRisk.INVESTMENT_QUESTION


@pytest.mark.parametrize(
    "text", ["what is the gold rate today", "how much loan for 30 grams", "book a visit"]
)
def test_gold_questions_that_are_not_advice_pass(text: str) -> None:
    assert check_input(text, "en").risk is None


# --- output: never ask for a secret ---


@pytest.mark.parametrize(
    "reply",
    [
        "Please share your OTP to continue.",
        "Tell me the OTP you received.",
        "What is your PIN?",
        "Can you confirm your password?",
        "Your OTP please.",
        "कृपया अपना ओटीपी बताइए",
    ],
)
def test_reply_asking_for_a_secret_is_blocked(reply: str) -> None:
    assert Violation.ASKS_FOR_SECRET in find_violations(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "Muthoot will never ask for your OTP, PIN, CVV or password.",
        "Never share your OTP with anyone.",
        "Please don't share your PIN with anyone.",
        "Please tell me the pin code of your area.",
    ],
)
def test_safety_advice_about_secrets_is_allowed(reply: str) -> None:
    assert not find_violations(reply)


# --- output: never promise ---


@pytest.mark.parametrize(
    "reply",
    [
        "Your loan is approved!",
        "Your loan will be sanctioned today.",
        "You will get ₹2,47,500.",
        "You will definitely get the loan.",
        "This amount is guaranteed.",
        "We guarantee you will receive the full amount.",
        "The final amount is ₹2,40,000.",
        "आपका लोन मंज़ूर हो गया",
    ],
)
def test_promises_are_blocked(reply: str) -> None:
    assert Violation.PROMISE in find_violations(reply)


@pytest.mark.parametrize(
    "reply",
    [
        "For 30 g of 22 carat gold you could get about ₹2,22,700 to ₹2,47,500.",
        "This is an estimate only. The final loan amount is decided after valuation.",
        "Your loan ending 0004 has ₹70,000 outstanding.",
        "You could get a top-up of about ₹35,400, decided after valuation at the branch.",
    ],
)
def test_estimates_are_allowed(reply: str) -> None:
    assert not find_violations(reply)


# --- output: no investment advice ---


@pytest.mark.parametrize(
    "reply",
    [
        "You should buy gold now.",
        "It's a good time to sell.",
        "I recommend buying more gold.",
        "Gold prices will rise next month.",
    ],
)
def test_investment_advice_is_blocked(reply: str) -> None:
    assert Violation.INVESTMENT_ADVICE in find_violations(reply)


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_blocked_reply_is_replaced_whole_in_the_customers_language(language: str) -> None:
    guarded = guard_reply("Please share your OTP and you will get ₹2,47,500.", language)  # type: ignore[arg-type]

    assert guarded.blocked
    assert guarded.text == SAFE_FALLBACK[language]  # type: ignore[index]
    assert "OTP" not in guarded.text or language != "en"


# --- output: masking ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Call 9876543210", "Call XXXXXX3210"),
        ("Call +91 98765 43210", "Call XXXXXXXX3210"),
        ("Account 410000000004", "Account XXXXXXXX0004"),
        ("Account 4100 0000 0004", "Account XXXXXXXX0004"),
    ],
)
def test_mobile_and_account_numbers_are_masked(text: str, expected: str) -> None:
    assert mask_long_numbers(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Branch phone 0484-000-0001",  # a public landline
        "about ₹2,22,700 to ₹2,47,500",
        "ticket GL-7F3K2Q on 27 Oct 2026",
        "30 grams at ₹11,000 per gram",
    ],
)
def test_amounts_dates_and_branch_phones_are_left_alone(text: str) -> None:
    assert mask_long_numbers(text) == text


def test_guard_masks_a_reply_it_lets_through() -> None:
    guarded = guard_reply("We will call you on 9876543210.", "en")

    assert not guarded.blocked
    assert guarded.text == "We will call you on XXXXXX3210."
