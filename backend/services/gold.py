"""Gold rate and the loan estimate. Shared by the HTTP routes and (from M2) the loan
calculator agent.

The estimate is always a range, never a promise: the final amount is only known after
the gold is valued at a branch.
"""

from dataclasses import dataclass
from datetime import timedelta

from beanie import PydanticObjectId

from config import get_settings
from models.gold_rate import GoldRate
from models.loan_estimate import LoanEstimate
from time_utils import now_utc, today_ist

CARATS = (24, 22, 18)
ROUND_TO = 100  # rupees; the estimate is rounded down to this
REPEAT_WINDOW_MINUTES = 5

DISCLAIMER = (
    "This is an estimate only. The final loan amount is decided after your gold is "
    "valued at the branch."
)


@dataclass(frozen=True)
class Scheme:
    """An interest scheme. Mock names and rates: the real ones come from the client."""

    code: str
    name: str
    interest_rate_pa: float  # percent per year
    repayment: str


SCHEMES = [
    Scheme("saver", "Saver", 12.0, "Pay interest every month"),
    Scheme("flexi", "Flexi", 14.0, "Pay interest every quarter"),
    Scheme("bullet", "Bullet", 18.0, "Pay principal and interest together at maturity"),
]


@dataclass(frozen=True)
class SchemeOption:
    scheme: Scheme
    monthly_interest_low: int  # rupees, on the low and high ends of the estimate
    monthly_interest_high: int


@dataclass(frozen=True)
class Estimate:
    grams: float
    carat: int
    rate_24k_per_gram: int
    rate_per_gram: int  # for this carat
    gold_value: int
    ltv_limit: float
    low: int
    high: int
    schemes: list[SchemeOption]
    disclaimer: str = DISCLAIMER


async def current_rate_24k() -> int:
    """Today's rate if an admin has set one, otherwise the configured rate."""
    today = await GoldRate.find_one(GoldRate.day == today_ist().isoformat())
    return today.rate_24k_per_gram if today else get_settings().gold_rate_24k_per_gram


def rupees(amount: int) -> str:
    """Indian digit grouping, as customers read it: 247500 -> ₹2,47,500."""
    sign, digits = ("-", str(-amount)) if amount < 0 else ("", str(amount))
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        head, group = head[:-2], head[-2:]
        groups.insert(0, group)
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join([*groups, tail])}"


def rate_for_carat(rate_24k: int, carat: int) -> int:
    return round(rate_24k * carat / 24)


def _round_down(amount: float) -> int:
    return int(amount // ROUND_TO * ROUND_TO)


def calculate(grams: float, carat: int, rate_24k: int) -> Estimate:
    """grams × purity × rate × LTV limit, as a range. Pure: no database."""
    if carat not in CARATS:
        raise ValueError(f"carat must be one of {CARATS}")
    if grams <= 0:
        raise ValueError("grams must be positive")
    settings = get_settings()
    gold_value = grams * rate_24k * carat / 24
    high = gold_value * settings.ltv_limit
    low = high * (1 - settings.estimate_deduction)
    schemes = [
        SchemeOption(
            scheme=scheme,
            monthly_interest_low=round(_round_down(low) * scheme.interest_rate_pa / 100 / 12),
            monthly_interest_high=round(_round_down(high) * scheme.interest_rate_pa / 100 / 12),
        )
        for scheme in SCHEMES
    ]
    return Estimate(
        grams=grams,
        carat=carat,
        rate_24k_per_gram=rate_24k,
        rate_per_gram=rate_for_carat(rate_24k, carat),
        gold_value=round(gold_value),
        ltv_limit=settings.ltv_limit,
        low=_round_down(low),
        high=_round_down(high),
        schemes=schemes,
    )


async def estimate(
    grams: float, carat: int, customer_id: PydanticObjectId | None = None
) -> tuple[Estimate, LoanEstimate]:
    """Work out an estimate at today's rate and record it, so a later visit counts as a lead.

    The same customer asking the same thing again within a few minutes (a retry, or the
    rule-based fallback redoing a turn) is one estimate, not two."""
    result = calculate(grams, carat, await current_rate_24k())
    if customer_id is not None:
        recent = await LoanEstimate.find_one(
            LoanEstimate.customer_id == customer_id,
            LoanEstimate.grams == grams,
            LoanEstimate.carat == carat,
            LoanEstimate.created_at >= now_utc() - timedelta(minutes=REPEAT_WINDOW_MINUTES),
        )
        if recent is not None:
            return result, recent
    record = LoanEstimate(
        customer_id=customer_id,
        grams=grams,
        carat=carat,
        rate_24k_per_gram=result.rate_24k_per_gram,
        low=result.low,
        high=result.high,
    )
    await record.insert()
    return result, record
