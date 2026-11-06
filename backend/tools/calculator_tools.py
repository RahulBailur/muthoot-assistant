"""The loan estimate. Always a range at today's rate, never a promise."""

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field

from services import gold
from services.gold import rupees
from tools import Tool, ToolArgs, ToolContext, ToolResult, schema
from tools.branch_tools import GET_GOLD_RATE

GRAMS_PER_PAVAN = 8.0  # a pavan (sovereign), the unit most Kerala and Tamil customers use
GRAMS_PER_TOLA = 11.66

# Number words a customer may say instead of digits (STT often writes them out)
NUMBER_WORDS: dict[str, int] = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "twenty five": 25, "thirty": 30,
    "forty": 40, "fifty": 50, "hundred": 100,
    # Hindi, romanised
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "pandrah": 15, "bees": 20, "pachees": 25,
    "pachchis": 25, "tees": 30, "chalis": 40, "chaalis": 40, "pachas": 50, "pachaas": 50,
    "sau": 100,
    # Hindi, Devanagari
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "सात": 7, "आठ": 8,
    "नौ": 9, "दस": 10, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40,
    "पचास": 50, "सौ": 100,
}  # fmt: skip

_NUMBER = (
    r"(?P<number>\d+(?:\.\d+)?|"
    + "|".join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True))
    + r")"
)
# Latin units must end there ("30 gold" is not 30 g); Indic units take case endings
_GRAMS = r"(?:grams?|grammes?|gms?|gm|g(?![a-z])|ग्राम|ಗ್ರಾಂ|ഗ്രാം|கிராம்)"
_PAVAN = r"(?:pavan|pavun|pawan|sovereigns?|पवन|ಪವನ್|പവൻ|പവന|பவுன்)"
_TOLA = r"(?:tolas?|तोला|तोले)"
_QUANTITY = re.compile(
    rf"(?<![\w.]){_NUMBER}\s*(?:(?P<grams>{_GRAMS})|(?P<pavan>{_PAVAN})|(?P<tola>{_TOLA}))"
)
_CARAT = re.compile(r"(?<!\d)(?P<carat>18|22|24)\s*(?:carats?|karats?|kt|k|ct|कैरेट|ಕ್ಯಾರೆಟ್|കാരറ്റ്|கேரட்)")


@dataclass(frozen=True)
class GoldAmount:
    grams: float | None
    carat: Literal[18, 22, 24] | None


def parse_gold(text: str) -> GoldAmount:
    """Grams and carat as the customer said them, e.g. "30 gram", "4 pavan", "22 carat"."""
    lowered = text.lower()
    grams: float | None = None
    if match := _QUANTITY.search(lowered):
        word = match.group("number")
        number = float(word) if word[0].isdigit() else float(NUMBER_WORDS[word])
        if match.group("pavan"):
            number *= GRAMS_PER_PAVAN
        elif match.group("tola"):
            number *= GRAMS_PER_TOLA
        grams = round(number, 2) if number > 0 else None
    carat_match = _CARAT.search(lowered)
    carat = int(carat_match.group("carat")) if carat_match else None
    return GoldAmount(grams, carat)  # type: ignore[arg-type]


class EstimateArgs(ToolArgs):
    grams: float = Field(gt=0, le=1000)
    carat: Literal[18, 22, 24] = 22  # most jewellery is 22 carat


async def estimate_loan(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    parsed = EstimateArgs.model_validate(args)
    customer_id = context.user.id if context.is_customer else None
    result, _ = await gold.estimate(parsed.grams, parsed.carat, customer_id)
    return {
        "grams": result.grams,
        "carat": result.carat,
        "rate_per_gram": rupees(result.rate_per_gram),
        "gold_value": rupees(result.gold_value),
        "loan_low": rupees(result.low),
        "loan_high": rupees(result.high),
        "ltv_limit_percent": round(result.ltv_limit * 100),
        "schemes": [
            {
                "name": option.scheme.name,
                "interest_rate_pa_percent": option.scheme.interest_rate_pa,
                "repayment": option.scheme.repayment,
                "monthly_interest": (
                    f"{rupees(option.monthly_interest_low)} to "
                    f"{rupees(option.monthly_interest_high)}"
                ),
            }
            for option in result.schemes
        ],
        "say_it_as": "a range, 'about loan_low to loan_high', and that it is an estimate",
        "disclaimer": result.disclaimer,
    }


ESTIMATE_LOAN = Tool(
    "estimate_loan",
    "Estimate the loan range for some gold at today's rate, with the interest schemes. "
    "Records the estimate.",
    schema(
        {
            "grams": {"type": "number", "description": "Weight in grams (1 pavan = 8 g)."},
            "carat": {
                "type": "integer",
                "enum": [24, 22, 18],
                "description": "Purity. Default 22 if the customer does not say.",
            },
        },
        ["grams"],
    ),
    estimate_loan,
)

CALCULATOR_TOOLS: tuple[Tool, ...] = (ESTIMATE_LOAN, GET_GOLD_RATE)
