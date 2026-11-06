from datetime import date, datetime, time, timedelta
from typing import Any

from httpx import AsyncClient

from auth_utils import create_access_token, hash_password
from models.branch import Branch
from models.loan_account import LoanAccount
from models.user import Role, User
from time_utils import IST, as_utc, today_ist

STAFF_PASSWORD = "staff-password-1"

_counter = 0


def _next() -> int:
    global _counter
    _counter += 1
    return _counter


async def make_branch(city: str = "Kochi") -> Branch:
    """A branch open 09:30–17:30 every day of the week, 30-minute slots."""
    number = _next()
    branch = Branch(
        code=f"TST{number:02d}",
        name=f"Test Branch {number}",
        city=city,
        address="1 Test Street",
        pincode="682011",
        phone="0484-000-0000",
        open_weekdays=list(range(7)),
    )
    await branch.insert()
    return branch


async def make_user(
    role: Role = Role.CUSTOMER, branch: Branch | None = None, name: str | None = None
) -> User:
    number = _next()
    user = User(
        name=name or f"{role.value.title()} {number}",
        phone=f"8{number:09d}",
        role=role,
        password_hash=hash_password(STAFF_PASSWORD) if role != Role.CUSTOMER else None,
        branch_id=branch.id if branch else None,
    )
    await user.insert()
    return user


async def make_loan(customer: User, branch: Branch, **overrides: Any) -> LoanAccount:
    assert customer.id is not None and branch.id is not None
    today = today_ist()
    fields: dict[str, Any] = {
        "customer_id": customer.id,
        "branch_id": branch.id,
        "account_number": f"4100{_next():08d}",
        "scheme": "Saver",
        "principal": 100_000,
        "outstanding": 100_000,
        "interest_rate_pa": 12.0,
        "interest_due": 1000,
        "gold_weight_grams": 20.0,
        "purity_carat": 22,
        "opened_on": today - timedelta(days=100),
        "next_due_date": today + timedelta(days=20),
        "maturity_date": today + timedelta(days=200),
    }
    fields.update(overrides)
    loan = LoanAccount(**fields)
    await loan.insert()
    return loan


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def slot(days_ahead: int, index: int = 0) -> datetime:
    """UTC start of the Nth valuation slot, `days_ahead` days from today (IST)."""
    day: date = today_ist() + timedelta(days=days_ahead)
    start = datetime.combine(day, time(9, 30), tzinfo=IST) + timedelta(minutes=30 * index)
    return as_utc(start)


async def otp_login(client: AsyncClient, phone: str, name: str | None = None) -> dict[str, Any]:
    """Log a customer in the way the app does: request an OTP, then verify it."""
    sent = await client.post("/api/auth/otp/request", json={"phone": phone})
    assert sent.status_code == 200, sent.text
    body: dict[str, Any] = {"phone": phone, "otp": sent.json()["demo_otp"]}
    if name:
        body["name"] = name
    verified = await client.post("/api/auth/otp/verify", json=body)
    assert verified.status_code == 200, verified.text
    result: dict[str, Any] = verified.json()
    return result
