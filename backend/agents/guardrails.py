"""Financial safety guardrails, on what the customer says and on what the assistant says.

Input (before any model sees the turn):
- A customer trying to share an OTP, PIN, CVV or password gets the warning, and the digits
  are redacted before the text is stored anywhere.
- "Should I buy or sell gold now?" gets a polite refusal: no investment advice.

Output (every reply, whichever agent or model wrote it):
- Never ask for an OTP, PIN, CVV or password.
- Never promise approval or a final amount.
- No investment advice.
A reply that breaks one of these is replaced whole, not edited. Long digit runs (phone or
account numbers) are masked to their last four digits in every reply.

Pattern-based, so it is a backstop and not a proof. English coverage is the strongest;
the other languages cover the commonest words and phrasings.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from agents.intent_classifier import normalise
from agents.languages import (
    ESTIMATE_DISCLAIMER,
    INVESTMENT_REFUSAL,
    SAFE_FALLBACK,
    SECRET_WARNING,
    Language,
)


class Violation(StrEnum):
    ASKS_FOR_SECRET = "asks_for_secret"
    PROMISE = "promise"
    INVESTMENT_ADVICE = "investment_advice"


class InputRisk(StrEnum):
    SHARES_SECRET = "shares_secret"
    INVESTMENT_QUESTION = "investment_question"


# The words for a secret, in every language we speak
_SECRET_WORDS = (
    r"otp|one time password|m?pin|cvv|cvc|password|passcode|passwd|"
    r"ओटीपी|पिन|पासवर्ड|ಒಟಿಪಿ|ಓಟಿಪಿ|ಪಿನ್|ಪಾಸ್‌?ವರ್ಡ್|ഒടിപി|ഒ ടി പി|പിൻ|പാസ്‌?വേഡ്|"
    r"ஓடிபி|ஓ டி பி|பின்|கடவுச்சொல்|பாஸ்வேர்ட்"
)
# "pin code" is a postal code, not a PIN
_NOT_A_SECRET = r"(?!\s*(code|कोड|ಕೋಡ್|കോഡ്|கோட்))"
_SECRET = re.compile(rf"(?<!\w)({_SECRET_WORDS})(?!\w){_NOT_A_SECRET}")
_DIGITS = re.compile(r"\d[\d\s-]{2,}\d|\d{3,}")
# "my password is tiger123": a password need not be digits
_PASSWORD_GIVEN = re.compile(r"\b(password|passcode|पासवर्ड)\s*(is|hai|है|:)\s*\S+")

_INVESTMENT_QUESTION = re.compile(
    r"\b(should|shall|can) i (buy|sell|invest|purchase|keep|hold)\b.{0,30}\bgold|"
    r"\b(good|right|best) time to (buy|sell|invest)|"
    r"\bgold (price|rate)s? (will|going to|go) (go )?(up|down|rise|fall|increase|decrease)|"
    r"\bwill (the )?gold (price|rate) (go up|go down|rise|fall|increase|decrease)|"
    r"\b(invest|investment) (in|on) gold|"
    r"\b(sona|gold) (khareed|kharid|bech)\w*|"
    r"सोना (खरीद|बेच)|सोने में निवेश|ಚಿನ್ನ (ಖರೀದಿ|ಮಾರ)|ಚಿನ್ನದಲ್ಲಿ ಹೂಡಿಕೆ|"
    r"സ്വർണം (വാങ്ങ|വിൽക്ക)|സ്വർണത്തിൽ നിക്ഷേപ|தங்கம் (வாங்க|விற்க)|தங்கத்தில் முதலீடு"
)

_OUTPUT_PATTERNS: list[tuple[Violation, re.Pattern[str]]] = [
    # --- asking for a secret ---
    (
        Violation.ASKS_FOR_SECRET,
        re.compile(
            # "never share your OTP" is good advice, not a request
            r"(?<!never )(?<!not )(?<!don t )(?<!dont )"
            rf"\b(share|tell|give|send|provide|enter|type|say|read out|confirm)\b"
            rf"(\s+\w+){{0,3}}\s+({_SECRET_WORDS})\b{_NOT_A_SECRET}|"
            rf"\b(what is|what s) your ({_SECRET_WORDS})\b{_NOT_A_SECRET}|"
            rf"\b(your|the) ({_SECRET_WORDS}) (please|number)\b|"
            r"(ओटीपी|पिन|पासवर्ड) (बताइए|बताएं|बताओ|दीजिए|भेजिए)|"
            r"(ಒಟಿಪಿ|ಪಿನ್)\S* (ಹೇಳಿ|ಕೊಡಿ|ಕಳುಹಿಸಿ)|(ഒടിപി|പിൻ)\S* (പറയൂ|തരൂ|അയക്കൂ)|"
            r"(ஓடிபி|பின்)\S* (சொல்லுங்கள்|கொடுங்கள்|அனுப்புங்கள்)"
        ),
    ),
    # --- promising approval or a final amount ---
    (
        Violation.PROMISE,
        re.compile(
            r"\b(guarantee[sd]?|assured(ly)?|pre ?approved|100 percent|definitely|certainly) "
            r"(\w+ ){0,3}(get|receive|approv\w*|sanction\w*|loan|amount)|"
            r"\b(will (surely |definitely |certainly )?be|is sure to be|is guaranteed to be) "
            r"(approved|sanctioned)\b|"
            r"\b(loan|top ?up|amount) (is|has been) (approved|sanctioned)\b|"
            r"\b(is|are) (guaranteed|assured)\b|"
            # An exact amount promised; "you could get about ₹X to ₹Y" is fine
            r"\byou will (definitely |surely )?(get|receive) (exactly |the full )?(rs )?\d|"
            r"\bfinal (loan )?amount (is|will be) (rs )?\d|"
            r"(मंज़ूर|मंजूर|स्वीकृत) (हो गया|हो जाएगा)|पक्का मिलेगा|गारंटी है|गारंटीड|"
            r"ಖಚಿತವಾಗಿ ಸಿಗುತ್ತದೆ|ಮಂಜೂರಾಗಿದೆ|ഉറപ്പായും ലഭിക്കും|അനുവദിച്ചു|"
            r"நிச்சயமாக கிடைக்கும்|அனுமதிக்கப்பட்டது"
        ),
    ),
    # --- investment advice ---
    (
        Violation.INVESTMENT_ADVICE,
        re.compile(
            r"\byou should (buy|sell|invest|hold|keep)\b|"
            r"\b(good|right|best|great) time to (buy|sell|invest)|"
            r"\b(i|we) (recommend|suggest|advise) (buying|selling|investing|holding)|"
            r"\bgold (price|rate)s? (will|is going to|are going to) (rise|fall|go up|go down|"
            r"increase|decrease)|"
            r"(खरीद|बेच) (लीजिए|दीजिए|लें|दें)|सही समय है"
        ),
    ),
]

# A customer's mobile number (10 digits from 6-9, maybe +91) or an account number (12 or
# more digits), possibly broken by spaces or dashes. Branch landlines start with 0 and are
# public, so they are left alone.
# Not part of a longer number, an amount ("2,47,500") or a decimal; a full stop after is fine.
_NOT_BEFORE = r"(?<!\d)(?<!\d[.,])"
_NOT_AFTER = r"(?!\d|[.,]\d)"
_MOBILE = re.compile(rf"{_NOT_BEFORE}(?:\+?91[ -]?)?[6-9](?:[ -]?\d){{9}}{_NOT_AFTER}")
_ACCOUNT = re.compile(rf"{_NOT_BEFORE}\d(?:[ -]?\d){{11,}}{_NOT_AFTER}")


@dataclass(frozen=True)
class InputCheck:
    risk: InputRisk | None
    reply: str | None  # said instead of running an agent, when risky
    stored_text: str  # what may be kept in conversation memory


@dataclass(frozen=True)
class GuardedReply:
    text: str
    blocked: bool
    violations: tuple[Violation, ...]


def redact_secrets(text: str) -> str:
    """The text with any digits near a secret word, and any stated password, removed."""
    if not _SECRET.search(normalise(text)):
        return text
    redacted = _PASSWORD_GIVEN.sub(lambda m: f"{m.group(1)} {m.group(2)} [redacted]", text)
    return _DIGITS.sub("[redacted]", redacted)


def shares_secret(text: str) -> bool:
    """A secret word together with digits (or a stated password): an attempt to share one."""
    clean = normalise(text)
    if not _SECRET.search(clean):
        return False
    return bool(_DIGITS.search(text) or _PASSWORD_GIVEN.search(text.lower()))


def asks_investment_advice(text: str) -> bool:
    return bool(_INVESTMENT_QUESTION.search(normalise(text)))


def check_input(text: str, language: Language) -> InputCheck:
    """What to do with a customer's message before any agent or model sees it."""
    if shares_secret(text):
        return InputCheck(InputRisk.SHARES_SECRET, SECRET_WARNING[language], redact_secrets(text))
    if asks_investment_advice(text):
        return InputCheck(InputRisk.INVESTMENT_QUESTION, INVESTMENT_REFUSAL[language], text)
    return InputCheck(None, None, text)


def find_violations(text: str) -> tuple[Violation, ...]:
    clean = normalise(text.replace("₹", " rs ").replace("%", " percent"))
    found = {violation for violation, pattern in _OUTPUT_PATTERNS if pattern.search(clean)}
    return tuple(sorted(found))


def mask_long_numbers(text: str) -> str:
    """Mobile and account numbers keep their last four digits only."""

    def mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        return "X" * (len(digits) - 4) + digits[-4:]

    return _ACCOUNT.sub(mask, _MOBILE.sub(mask, text))


def guard_reply(text: str, language: Language) -> GuardedReply:
    """What may actually be shown or spoken, whichever agent or model wrote it."""
    violations = find_violations(text)
    if violations:
        return GuardedReply(SAFE_FALLBACK[language], True, violations)
    return GuardedReply(mask_long_numbers(text), False, ())


def estimate_disclaimer(language: Language) -> str:
    return ESTIMATE_DISCLAIMER[language]
