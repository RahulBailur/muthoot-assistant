"""Seed mock data: branches, branch staff, an admin, customers, loan accounts, visits, a ticket.

Everything here is invented. No real customers, account numbers or branch addresses.
Loan dates are set relative to today, so every kind of reminder has an example.
Safe to run more than once: existing records are left untouched.

    python scripts/seed_data.py
"""

import asyncio
from datetime import UTC, date, datetime, time, timedelta

from auth_utils import hash_password
from config import get_settings
from database import close_db, init_db
from models.branch import Branch
from models.branch_visit import BranchVisit, VisitStatus
from models.loan_account import LoanAccount, LoanStatus
from models.ticket import Ticket, TicketKind
from models.user import Role, User
from time_utils import IST, today_ist

# (code, name, city, address, pincode, phone)
BRANCHES = [
    (
        "KOC01",
        "Kochi MG Road (demo)",
        "Kochi",
        "1 Sample Street, MG Road",
        "682011",
        "0484-000-0001",
    ),
    (
        "TVM01",
        "Thiruvananthapuram Statue (demo)",
        "Thiruvananthapuram",
        "2 Sample Street, Statue Junction",
        "695001",
        "0471-000-0002",
    ),
    (
        "BLR01",
        "Bengaluru Jayanagar (demo)",
        "Bengaluru",
        "3 Sample Road, Jayanagar",
        "560041",
        "080-000-0003",
    ),
    (
        "CHN01",
        "Chennai T. Nagar (demo)",
        "Chennai",
        "4 Sample Road, T. Nagar",
        "600017",
        "044-000-0004",
    ),
    ("MUM01", "Mumbai Dadar (demo)", "Mumbai", "5 Sample Marg, Dadar", "400014", "022-000-0005"),
]

# (name, phone, branch code); one staff member per branch
STAFF = [
    ("Anil Varghese", "9000000101", "KOC01"),
    ("Sreeja Nair", "9000000102", "TVM01"),
    ("Manjunath Rao", "9000000103", "BLR01"),
    ("Karthik Subramanian", "9000000104", "CHN01"),
    ("Pooja Deshmukh", "9000000105", "MUM01"),
]

ADMIN = ("Demo Admin", "9000000100")

# (name, phone, preferred language, branch code)
CUSTOMERS = [
    ("Lakshmi Nair", "9000000201", "ml", "KOC01"),
    ("Arjun Menon", "9000000202", "en", "TVM01"),
    ("Fatima Sheikh", "9000000203", "kn", "BLR01"),
    ("Ravi Kumar", "9000000204", "ta", "CHN01"),
    ("Sunita Patil", "9000000205", "hi", "MUM01"),
]

# Per customer: (grams, carat, principal, rate % p.a., scheme, days to next due date,
# days to maturity, status). Chosen so each reminder kind shows up.
LOANS = [
    (30.0, 22, 200_000, 12.0, "Saver", 3, 180, LoanStatus.ACTIVE),  # interest due soon
    (20.0, 22, 120_000, 14.0, "Flexi", -10, 120, LoanStatus.ACTIVE),  # interest overdue
    (45.0, 22, 300_000, 12.0, "Saver", 15, 20, LoanStatus.ACTIVE),  # matures soon
    (15.0, 18, 70_000, 18.0, "Bullet", -10, -10, LoanStatus.ACTIVE),  # auction warning
    (12.0, 24, 0, 12.0, "Saver", -200, -200, LoanStatus.CLOSED),  # closed: no reminders
]

SLOT_MINUTES = 30


def _account_number(index: int) -> str:
    return f"4100{index + 1:08d}"  # 12 digits, obviously fake


async def _get_or_create_user(
    name: str,
    phone: str,
    role: Role,
    password_hash: str | None = None,
    branch: Branch | None = None,
    language: str = "en",
) -> tuple[User, bool]:
    existing = await User.find_one(User.phone == phone)
    if existing:
        return existing, False
    user = User(
        name=name,
        phone=phone,
        role=role,
        password_hash=password_hash,
        branch_id=branch.id if branch else None,
        preferred_language=language,
    )
    await user.insert()
    return user, True


def _slot(branch: Branch, day: date, index: int) -> tuple[datetime, datetime]:
    """UTC start/end of the Nth valuation slot on the given IST day."""
    opening = datetime.combine(day, time.fromisoformat(branch.open_time), tzinfo=IST)
    start = opening + timedelta(minutes=branch.slot_minutes * index)
    end = start + timedelta(minutes=branch.slot_minutes)
    return start.astimezone(UTC), end.astimezone(UTC)


async def seed() -> dict[str, int]:
    """Insert the mock dataset. Returns how many records of each kind were created."""
    settings = get_settings()
    if not settings.seed_default_password:
        raise RuntimeError("Set SEED_DEFAULT_PASSWORD in .env before seeding")
    password_hash = hash_password(settings.seed_default_password)
    created = {"branches": 0, "users": 0, "loans": 0, "visits": 0, "tickets": 0}

    branches: dict[str, Branch] = {}
    for code, name, city, address, pincode, phone in BRANCHES:
        branch = await Branch.find_one(Branch.code == code)
        if branch is None:
            branch = Branch(
                code=code,
                name=name,
                city=city,
                address=address,
                pincode=pincode,
                phone=phone,
                slot_minutes=SLOT_MINUTES,
            )
            await branch.insert()
            created["branches"] += 1
        branches[code] = branch

    for name, phone, code in STAFF:
        _, is_new = await _get_or_create_user(
            name, phone, Role.STAFF, password_hash, branches[code]
        )
        created["users"] += is_new

    _, is_new = await _get_or_create_user(*ADMIN, Role.ADMIN, password_hash)
    created["users"] += is_new

    today = today_ist()
    customers: list[User] = []
    for index, (name, phone, language, code) in enumerate(CUSTOMERS):
        customer, is_new = await _get_or_create_user(name, phone, Role.CUSTOMER, language=language)
        customers.append(customer)
        created["users"] += is_new

        grams, carat, principal, rate, scheme, to_due, to_maturity, status = LOANS[index]
        number = _account_number(index)
        if customer.id is None or branches[code].id is None:
            continue
        if await LoanAccount.find_one(LoanAccount.account_number == number):
            continue
        maturity = today + timedelta(days=to_maturity)
        await LoanAccount(
            customer_id=customer.id,
            branch_id=branches[code].id,
            account_number=number,
            scheme=scheme,
            principal=principal or 50_000,
            outstanding=principal,
            interest_rate_pa=rate,
            interest_due=round(principal * rate / 100 / 12),
            gold_weight_grams=grams,
            purity_carat=carat,
            opened_on=maturity - timedelta(days=365),
            next_due_date=today + timedelta(days=to_due),
            maturity_date=maturity,
            status=status,
        ).insert()
        created["loans"] += 1

    # Three customers have valuation slots at the Kochi branch today, so its queue has
    # something to show
    kochi = branches["KOC01"]
    for index, customer in enumerate(customers[:3]):
        start, end = _slot(kochi, today, index)
        exists = await BranchVisit.find_one(
            BranchVisit.branch_id == kochi.id, BranchVisit.slot_start == start
        )
        if exists or customer.id is None or kochi.id is None:
            continue
        await BranchVisit(
            customer_id=customer.id,
            branch_id=kochi.id,
            slot_start=start,
            slot_end=end,
            status=VisitStatus.BOOKED,
        ).insert()
        created["visits"] += 1

    # One open callback request, from the customer whose interest is overdue
    caller = customers[1]
    if caller.id is not None and await Ticket.find_one(Ticket.customer_id == caller.id) is None:
        tvm = branches["TVM01"]
        if tvm.id is not None:
            await Ticket(
                reference="GL-DEMO01",
                customer_id=caller.id,
                branch_id=tvm.id,
                kind=TicketKind.CALLBACK,
                message="Please call me about paying the overdue interest.",
                preferred_time="after 4 pm",
            ).insert()
            created["tickets"] += 1

    return created


async def main() -> None:
    await init_db()
    try:
        created = await seed()
    finally:
        close_db()
    for kind, count in created.items():
        print(f"{kind}: {count} created")


if __name__ == "__main__":
    asyncio.run(main())
