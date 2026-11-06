from httpx import AsyncClient

from models.branch import Branch
from models.branch_visit import BranchVisit
from models.loan_account import LoanAccount
from models.ticket import Ticket
from models.user import Role, User
from scripts.seed_data import BRANCHES, CUSTOMERS, LOANS, STAFF, seed, seed_if_empty
from services.loans import ReminderKind, reminders_for
from time_utils import today_ist


async def test_seed_creates_the_mock_dataset(client: AsyncClient) -> None:
    created = await seed()

    assert await Branch.count() == created["branches"] == len(BRANCHES)
    assert await User.find(User.role == Role.STAFF).count() == len(STAFF)
    assert await User.find(User.role == Role.ADMIN).count() == 1
    assert await User.find(User.role == Role.CUSTOMER).count() == len(CUSTOMERS)
    assert await LoanAccount.count() == len(LOANS)
    assert await BranchVisit.count() == 3
    assert await Ticket.count() == 1

    staff = await User.find(User.role == Role.STAFF).to_list()
    assert all(member.branch_id and member.password_hash for member in staff)
    customers = await User.find(User.role == Role.CUSTOMER).to_list()
    assert all(customer.password_hash is None for customer in customers)


async def test_seed_has_each_reminder_up_to_the_auction_warning(client: AsyncClient) -> None:
    await seed()

    today = today_ist()
    kinds = {
        reminder.kind
        for account in await LoanAccount.find_all().to_list()
        for reminder in reminders_for(account, today)
    }

    assert kinds == {
        ReminderKind.INTEREST_DUE_SOON,
        ReminderKind.INTEREST_OVERDUE,
        ReminderKind.MATURITY_SOON,
        ReminderKind.AUCTION_WARNING,
    }


async def test_seed_is_idempotent(client: AsyncClient) -> None:
    await seed()
    users, loans = await User.count(), await LoanAccount.count()

    second = await seed()

    assert second == {"branches": 0, "users": 0, "loans": 0, "visits": 0, "tickets": 0}
    assert await User.count() == users
    assert await LoanAccount.count() == loans


async def test_seeded_staff_can_log_in(client: AsyncClient) -> None:
    await seed()

    response = await client.post(
        "/api/auth/login", json={"phone": STAFF[0][1], "password": "seed-password-1"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "staff"


async def test_seed_on_start_fills_only_an_empty_database(client: AsyncClient) -> None:
    assert await seed_if_empty() is True
    users = await User.count()

    assert await seed_if_empty() is False
    assert await User.count() == users
