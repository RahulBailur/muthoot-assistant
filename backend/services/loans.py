"""Loan account views and reminders, shared by the HTTP routes and (from M2) the account agent.

Accounts are only ever looked up for the verified customer, and the account number only
leaves here masked.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from beanie import PydanticObjectId

from config import get_settings
from models.loan_account import LoanAccount, LoanStatus
from models.user import User
from privacy import last4, mask_account
from services.gold import ROUND_TO, current_rate_24k, rate_for_carat
from time_utils import today_ist

DUE_SOON_DAYS = 7
MATURITY_SOON_DAYS = 30


class ReminderKind(StrEnum):
    INTEREST_DUE_SOON = "interest_due_soon"
    INTEREST_OVERDUE = "interest_overdue"
    MATURITY_SOON = "maturity_soon"
    # Matured and not renewed or closed: warn before the auction notice
    AUCTION_WARNING = "auction_warning"
    AUCTION_NOTICE_DUE = "auction_notice_due"


@dataclass(frozen=True)
class Reminder:
    kind: ReminderKind
    message: str
    days: int  # days left (or overdue, for the overdue kinds)


@dataclass(frozen=True)
class LoanView:
    id: str
    account_masked: str
    account_last4: str
    branch_id: str
    scheme: str
    principal: int
    outstanding: int
    interest_rate_pa: float
    interest_due: int
    gold_weight_grams: float
    purity_carat: int
    opened_on: date
    next_due_date: date
    maturity_date: date
    status: LoanStatus
    top_up_available: int  # extra loan the pledged gold supports at today's rate
    reminders: list[Reminder] = field(default_factory=list)


def reminders_for(account: LoanAccount, today: date) -> list[Reminder]:
    if account.status != LoanStatus.ACTIVE:
        return []
    reminders: list[Reminder] = []
    to_due = (account.next_due_date - today).days
    if to_due < 0:
        reminders.append(
            Reminder(
                ReminderKind.INTEREST_OVERDUE,
                f"Interest of ₹{account.interest_due:,} is {-to_due} days overdue.",
                -to_due,
            )
        )
    elif to_due <= DUE_SOON_DAYS:
        reminders.append(
            Reminder(
                ReminderKind.INTEREST_DUE_SOON,
                f"Interest of ₹{account.interest_due:,} is due in {to_due} days.",
                to_due,
            )
        )

    to_maturity = (account.maturity_date - today).days
    grace = get_settings().auction_grace_days
    if 0 <= to_maturity <= MATURITY_SOON_DAYS:
        reminders.append(
            Reminder(
                ReminderKind.MATURITY_SOON,
                f"Your loan matures in {to_maturity} days. Renew or close it before then.",
                to_maturity,
            )
        )
    elif to_maturity < 0 and -to_maturity <= grace:
        days_left = grace + to_maturity
        reminders.append(
            Reminder(
                ReminderKind.AUCTION_WARNING,
                f"Your loan has matured. Renew or close it within {days_left} days "
                "to avoid an auction notice.",
                days_left,
            )
        )
    elif to_maturity < 0:
        reminders.append(
            Reminder(
                ReminderKind.AUCTION_NOTICE_DUE,
                "Your loan is past maturity and an auction notice may be sent. "
                "Please contact your branch today.",
                -to_maturity - grace,
            )
        )
    return reminders


def top_up_available(account: LoanAccount, rate_24k: int) -> int:
    if account.status != LoanStatus.ACTIVE:
        return 0
    value = account.gold_weight_grams * rate_for_carat(rate_24k, account.purity_carat)
    limit = value * get_settings().ltv_limit
    return max(0, int((limit - account.outstanding) // ROUND_TO * ROUND_TO))


def view(account: LoanAccount, rate_24k: int, today: date) -> LoanView:
    return LoanView(
        id=str(account.id),
        account_masked=mask_account(account.account_number),
        account_last4=last4(account.account_number),
        branch_id=str(account.branch_id),
        scheme=account.scheme,
        principal=account.principal,
        outstanding=account.outstanding,
        interest_rate_pa=account.interest_rate_pa,
        interest_due=account.interest_due,
        gold_weight_grams=account.gold_weight_grams,
        purity_carat=account.purity_carat,
        opened_on=account.opened_on,
        next_due_date=account.next_due_date,
        maturity_date=account.maturity_date,
        status=account.status,
        top_up_available=top_up_available(account, rate_24k),
        reminders=reminders_for(account, today),
    )


async def accounts_for(customer: User) -> list[LoanView]:
    """The customer's own loans, active first."""
    accounts = await LoanAccount.find(LoanAccount.customer_id == customer.id).to_list()
    accounts.sort(key=lambda a: (a.status != LoanStatus.ACTIVE, a.maturity_date))
    rate, today = await current_rate_24k(), today_ist()
    return [view(account, rate, today) for account in accounts]


async def account_for(customer: User, account_id: PydanticObjectId) -> LoanView | None:
    """One of the customer's own loans. Anyone else's is None, the same as a missing one."""
    account = await LoanAccount.get(account_id)
    if account is None or account.customer_id != customer.id:
        return None
    return view(account, await current_rate_24k(), today_ist())
