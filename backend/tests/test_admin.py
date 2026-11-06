import pytest
from httpx import AsyncClient

from models.user import Role
from tests.helpers import auth, make_branch, make_loan, make_user, slot


async def test_stats_count_estimates_leads_and_branch_activity(client: AsyncClient) -> None:
    branch = await make_branch()
    admin = await make_user(Role.ADMIN)
    lead, browser = await make_user(), await make_user()
    await make_loan(lead, branch)
    await client.post("/api/gold/estimate", json={"grams": 30}, headers=auth(lead))
    await client.post("/api/gold/estimate", json={"grams": 10}, headers=auth(browser))
    await client.post(
        "/api/visits/book",
        json={"branch_id": str(branch.id), "slot_start": slot(1).isoformat()},
        headers=auth(lead),
    )
    await client.post(
        "/api/tickets",
        json={"kind": "callback", "message": "Please call"},
        headers=auth(lead),
    )

    response = await client.get("/api/admin/stats", headers=auth(admin))

    assert response.status_code == 200
    body = response.json()
    assert body["estimates"] == 2
    assert body["leads"] == 1
    assert body["lead_conversion"] == 0.5
    assert body["customers"] == 2
    assert body["active_loans"] == 1
    [row] = body["branches"]
    assert row["open_tickets"] == 1


@pytest.mark.guardrail
async def test_stats_hold_no_personal_data(client: AsyncClient) -> None:
    branch = await make_branch()
    admin = await make_user(Role.ADMIN)
    customer = await make_user(name="Lakshmi Nair")
    loan = await make_loan(customer, branch)

    response = await client.get("/api/admin/stats", headers=auth(admin))

    assert customer.phone not in response.text
    assert customer.name not in response.text
    assert loan.account_number[-4:] not in response.text


@pytest.mark.parametrize("role", [Role.CUSTOMER, Role.STAFF])
async def test_stats_are_admin_only(client: AsyncClient, role: Role) -> None:
    user = await make_user(role, await make_branch() if role == Role.STAFF else None)

    response = await client.get("/api/admin/stats", headers=auth(user))

    assert response.status_code == 403
