from datetime import timedelta

import pytest
from httpx import AsyncClient

from models.loan_account import LoanStatus
from models.user import Role
from services.loans import ReminderKind
from tests.helpers import auth, make_branch, make_loan, make_user, otp_login
from time_utils import today_ist


@pytest.mark.guardrail
async def test_customer_sees_own_loans_with_account_number_masked(client: AsyncClient) -> None:
    branch = await make_branch()
    customer = await make_user()
    loan = await make_loan(customer, branch)

    response = await client.get("/api/loans/me", headers=auth(customer))

    assert response.status_code == 200
    [body] = response.json()
    assert body["account_last4"] == loan.account_number[-4:]
    assert body["account_masked"] == "XXXXXXXX" + loan.account_number[-4:]
    assert loan.account_number not in response.text


@pytest.mark.guardrail
async def test_customer_never_sees_another_customers_loan(client: AsyncClient) -> None:
    branch = await make_branch()
    mine, theirs = await make_user(), await make_user()
    await make_loan(mine, branch)
    other = await make_loan(theirs, branch)

    listed = await client.get("/api/loans/me", headers=auth(mine))
    direct = await client.get(f"/api/loans/{other.id}", headers=auth(mine))

    assert len(listed.json()) == 1
    assert other.account_number[-4:] not in listed.text
    assert direct.status_code == 404  # the same as a loan that does not exist


@pytest.mark.guardrail
async def test_account_details_need_a_verified_login(client: AsyncClient) -> None:
    response = await client.get("/api/loans/me")

    assert response.status_code == 401


@pytest.mark.guardrail
@pytest.mark.parametrize("role", [Role.STAFF, Role.ADMIN])
async def test_staff_and_admin_cannot_read_loan_accounts(client: AsyncClient, role: Role) -> None:
    branch = await make_branch()
    user = await make_user(role, branch if role == Role.STAFF else None)
    loan = await make_loan(await make_user(), branch)

    listed = await client.get("/api/loans/me", headers=auth(user))
    direct = await client.get(f"/api/loans/{loan.id}", headers=auth(user))

    assert listed.status_code == direct.status_code == 403


async def test_otp_login_then_loan_details(client: AsyncClient) -> None:
    customer = await make_user()
    await make_loan(customer, await make_branch(), outstanding=80_000, interest_due=800)

    token = (await otp_login(client, customer.phone))["access_token"]
    response = await client.get("/api/loans/me", headers={"Authorization": f"Bearer {token}"})

    [body] = response.json()
    assert body["outstanding"] == 80_000
    assert body["interest_due"] == 800


def _kinds(body: dict[str, object]) -> set[str]:
    reminders = body["reminders"]
    assert isinstance(reminders, list)
    return {reminder["kind"] for reminder in reminders}


@pytest.mark.parametrize(
    ("due_in", "matures_in", "expected"),
    [
        (20, 200, set()),
        (3, 200, {ReminderKind.INTEREST_DUE_SOON}),
        (-5, 200, {ReminderKind.INTEREST_OVERDUE}),
        (20, 15, {ReminderKind.MATURITY_SOON}),
        (20, -10, {ReminderKind.AUCTION_WARNING}),
        (20, -45, {ReminderKind.AUCTION_NOTICE_DUE}),
    ],
)
async def test_reminders(
    client: AsyncClient, due_in: int, matures_in: int, expected: set[ReminderKind]
) -> None:
    customer = await make_user()
    today = today_ist()
    await make_loan(
        customer,
        await make_branch(),
        next_due_date=today + timedelta(days=due_in),
        maturity_date=today + timedelta(days=matures_in),
    )

    [body] = (await client.get("/api/loans/me", headers=auth(customer))).json()

    assert _kinds(body) == {kind.value for kind in expected}


async def test_auction_warning_says_how_many_days_are_left(client: AsyncClient) -> None:
    customer = await make_user()
    await make_loan(customer, await make_branch(), maturity_date=today_ist() - timedelta(days=10))

    [body] = (await client.get("/api/loans/me", headers=auth(customer))).json()

    [warning] = body["reminders"]
    assert warning["days"] == 20  # 30 grace days, 10 used
    assert "20 days" in warning["message"]


async def test_closed_loan_has_no_reminders_or_top_up(client: AsyncClient) -> None:
    customer = await make_user()
    await make_loan(
        customer,
        await make_branch(),
        status=LoanStatus.CLOSED,
        outstanding=0,
        next_due_date=today_ist() - timedelta(days=100),
        maturity_date=today_ist() - timedelta(days=100),
    )

    [body] = (await client.get("/api/loans/me", headers=auth(customer))).json()

    assert body["reminders"] == []
    assert body["top_up_available"] == 0


async def test_top_up_is_what_the_pledged_gold_supports_beyond_the_loan(
    client: AsyncClient,
) -> None:
    customer = await make_user()
    # 20 g of 22 carat at ₹11,000/g = ₹220,000; 75% = ₹165,000; owed ₹100,000
    await make_loan(customer, await make_branch(), outstanding=100_000)

    [body] = (await client.get("/api/loans/me", headers=auth(customer))).json()

    assert body["top_up_available"] == 65_000


async def test_active_loans_come_first(client: AsyncClient) -> None:
    customer = await make_user()
    branch = await make_branch()
    await make_loan(customer, branch, status=LoanStatus.CLOSED, outstanding=0)
    await make_loan(customer, branch)

    body = (await client.get("/api/loans/me", headers=auth(customer))).json()

    assert [loan["status"] for loan in body] == ["active", "closed"]
