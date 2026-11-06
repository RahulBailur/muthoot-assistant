import pytest
from httpx import AsyncClient

from models.loan_estimate import LoanEstimate
from models.user import Role
from services.gold import calculate
from tests.helpers import auth, make_branch, make_user

# conftest fixes the rate at ₹12,000/g for 24 carat, the LTV limit at 75% and the
# estimate's low end at 10% below its high end


async def test_rate_is_given_for_each_carat(client: AsyncClient) -> None:
    response = await client.get("/api/gold/rate")

    assert response.status_code == 200
    assert response.json()["rate_per_gram"] == {"24": 12000, "22": 11000, "18": 9000}


async def test_headline_estimate_30_grams_of_22_carat(client: AsyncClient) -> None:
    response = await client.post("/api/gold/estimate", json={"grams": 30, "carat": 22})

    assert response.status_code == 200
    body = response.json()
    assert body["rate_per_gram"] == 11000
    assert body["gold_value"] == 330_000
    assert body["high"] == 247_500  # 75% of the value
    assert body["low"] == 222_700  # 10% lower, rounded down to ₹100
    assert body["ltv_limit"] == 0.75


@pytest.mark.parametrize(("carat", "high"), [(24, 90_000), (22, 82_500), (18, 67_500)])
def test_purity_scales_the_estimate(carat: int, high: int) -> None:
    assert calculate(10, carat, 12000).high == high


def test_estimate_is_a_range_rounded_down_to_100() -> None:
    result = calculate(7.3, 22, 12000)

    assert result.low < result.high
    assert result.low % 100 == 0 and result.high % 100 == 0
    assert result.high <= result.gold_value * 0.75


async def test_estimate_lists_scheme_options_with_monthly_interest(client: AsyncClient) -> None:
    body = (await client.post("/api/gold/estimate", json={"grams": 30, "carat": 22})).json()

    saver = next(s for s in body["schemes"] if s["code"] == "saver")
    assert saver["interest_rate_pa"] == 12.0
    assert saver["monthly_interest_high"] == 2475  # 1% a month of 247,500
    assert saver["monthly_interest_low"] == 2227
    assert {s["code"] for s in body["schemes"]} == {"saver", "flexi", "bullet"}


@pytest.mark.guardrail
async def test_estimate_never_reads_as_a_promise(client: AsyncClient) -> None:
    body = (await client.post("/api/gold/estimate", json={"grams": 30, "carat": 22})).json()

    assert "estimate" in body["disclaimer"].lower()
    assert "valued at the branch" in body["disclaimer"]
    assert body["low"] != body["high"]  # a range, not one figure


async def test_carat_defaults_to_22(client: AsyncClient) -> None:
    body = (await client.post("/api/gold/estimate", json={"grams": 10})).json()

    assert body["carat"] == 22


@pytest.mark.parametrize(
    "body",
    [{"grams": 0}, {"grams": -5}, {"grams": 5000}, {"grams": 10, "carat": 20}, {"carat": 22}],
)
async def test_estimate_rejects_bad_input(client: AsyncClient, body: dict[str, object]) -> None:
    response = await client.post("/api/gold/estimate", json=body)

    assert response.status_code == 422


async def test_admin_can_set_todays_rate_and_estimates_use_it(client: AsyncClient) -> None:
    admin = await make_user(Role.ADMIN)

    response = await client.put(
        "/api/gold/rate", json={"rate_24k_per_gram": 13200}, headers=auth(admin)
    )
    again = await client.put(
        "/api/gold/rate", json={"rate_24k_per_gram": 14400}, headers=auth(admin)
    )

    assert response.status_code == again.status_code == 200
    assert again.json()["rate_per_gram"]["24"] == 14400
    estimate = (await client.post("/api/gold/estimate", json={"grams": 10, "carat": 24})).json()
    assert estimate["gold_value"] == 144_000


@pytest.mark.parametrize("role", [Role.CUSTOMER, Role.STAFF])
async def test_only_admin_sets_the_rate(client: AsyncClient, role: Role) -> None:
    user = await make_user(role, await make_branch() if role == Role.STAFF else None)

    response = await client.put(
        "/api/gold/rate", json={"rate_24k_per_gram": 1500}, headers=auth(user)
    )

    assert response.status_code == 403


async def test_estimates_are_recorded_with_the_customer_when_logged_in(
    client: AsyncClient,
) -> None:
    customer = await make_user(Role.CUSTOMER)

    await client.post("/api/gold/estimate", json={"grams": 10})
    await client.post("/api/gold/estimate", json={"grams": 20}, headers=auth(customer))

    estimates = await LoanEstimate.find_all().sort("+grams").to_list()
    assert [e.customer_id for e in estimates] == [None, customer.id]
