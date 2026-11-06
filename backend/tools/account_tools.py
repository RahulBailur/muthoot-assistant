"""The customer's own loan accounts. Only ever the session's customer, and only the last four
digits of an account number: that is all the model is ever given, so it is all it can say."""

from datetime import date
from typing import Any

from services import loans
from services.gold import rupees
from tools import CUSTOMERS_ONLY, Tool, ToolContext, ToolResult, schema


def say_date(day: date) -> str:
    return f"{day.day} {day:%b %Y}"


async def get_my_loans(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    if not context.is_customer:
        return CUSTOMERS_ONLY
    views = await loans.accounts_for(context.user)
    return {
        "loans": [
            {
                "account_ending": view.account_last4,
                "status": view.status.value,
                "scheme": view.scheme,
                "outstanding": rupees(view.outstanding),
                "interest_due": rupees(view.interest_due),
                "next_due_date": say_date(view.next_due_date),
                "maturity_date": say_date(view.maturity_date),
                "interest_rate_pa_percent": view.interest_rate_pa,
                "gold_weight_grams": view.gold_weight_grams,
                "top_up_estimate": rupees(view.top_up_available),
                "reminders": [reminder.message for reminder in view.reminders],
            }
            for view in views
        ]
    }


GET_MY_LOANS = Tool(
    "get_my_loans",
    "The logged-in customer's own gold loans: outstanding amount, interest due, due and "
    "maturity dates, reminders, and the top-up their gold supports at today's rate.",
    schema({}),
    get_my_loans,
)

ACCOUNT_TOOLS: tuple[Tool, ...] = (GET_MY_LOANS,)
