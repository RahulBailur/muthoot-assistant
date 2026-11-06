from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from auth_utils import AdminUser, OptionalUser
from models.gold_rate import GoldRate
from models.user import Role
from services import gold
from time_utils import now_utc, today_ist

router = APIRouter(prefix="/api/gold", tags=["gold"])


class RateOut(BaseModel):
    day: str
    rate_per_gram: dict[int, int]  # carat -> rupees


class RateRequest(BaseModel):
    rate_24k_per_gram: int = Field(gt=1000, lt=100_000)  # rupees; bounds catch typos


class EstimateRequest(BaseModel):
    grams: float = Field(gt=0, le=1000)
    carat: Literal[24, 22, 18] = 22  # most jewellery is 22 carat


class SchemeOut(BaseModel):
    code: str
    name: str
    interest_rate_pa: float
    repayment: str
    monthly_interest_low: int
    monthly_interest_high: int


class EstimateOut(BaseModel):
    grams: float
    carat: int
    rate_per_gram: int
    gold_value: int
    ltv_limit: float
    low: int
    high: int
    schemes: list[SchemeOut]
    disclaimer: str


async def _rate_out() -> RateOut:
    rate = await gold.current_rate_24k()
    return RateOut(
        day=today_ist().isoformat(),
        rate_per_gram={carat: gold.rate_for_carat(rate, carat) for carat in gold.CARATS},
    )


@router.get("/rate")
async def todays_rate() -> RateOut:
    """Today's gold rate per gram for 24, 22 and 18 carat. Public."""
    return await _rate_out()


@router.put("/rate")
async def set_todays_rate(admin: AdminUser, body: RateRequest) -> RateOut:
    """Set today's 24-carat rate. Admin only."""
    day = today_ist().isoformat()
    current = await GoldRate.find_one(GoldRate.day == day)
    if current is None:
        current = GoldRate(day=day, rate_24k_per_gram=body.rate_24k_per_gram)
    current.rate_24k_per_gram = body.rate_24k_per_gram
    current.set_by = admin.id
    current.updated_at = now_utc()
    await current.save()
    return await _rate_out()


@router.post("/estimate")
async def estimate(body: EstimateRequest, user: OptionalUser) -> EstimateOut:
    """Loan estimate range for some gold. Public; a logged-in customer's estimate is kept,
    so a visit they book afterwards counts as a lead."""
    customer_id = user.id if user and user.role == Role.CUSTOMER else None
    result, _ = await gold.estimate(body.grams, body.carat, customer_id)
    return EstimateOut(
        grams=result.grams,
        carat=result.carat,
        rate_per_gram=result.rate_per_gram,
        gold_value=result.gold_value,
        ltv_limit=result.ltv_limit,
        low=result.low,
        high=result.high,
        schemes=[
            SchemeOut(
                code=option.scheme.code,
                name=option.scheme.name,
                interest_rate_pa=option.scheme.interest_rate_pa,
                repayment=option.scheme.repayment,
                monthly_interest_low=option.monthly_interest_low,
                monthly_interest_high=option.monthly_interest_high,
            )
            for option in result.schemes
        ],
        disclaimer=result.disclaimer,
    )
