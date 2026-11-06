import pytest
from httpx import AsyncClient

from models.ticket import Ticket
from models.user import Role
from services.tickets import REFERENCE_ALPHABET
from tests.helpers import auth, make_branch, make_loan, make_user


async def test_callback_request_goes_to_the_customers_loan_branch(client: AsyncClient) -> None:
    branch = await make_branch()
    customer = await make_user()
    await make_loan(customer, branch)

    response = await client.post(
        "/api/tickets",
        json={"kind": "callback", "message": "Call me about renewal", "preferred_time": "4 pm"},
        headers=auth(customer),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["branch_id"] == str(branch.id)
    assert body["status"] == "open"
    assert body["reference"].startswith("GL-")
    assert all(ch in REFERENCE_ALPHABET for ch in body["reference"][3:])


async def test_ticket_without_a_loan_needs_a_branch(client: AsyncClient) -> None:
    customer = await make_user()
    branch = await make_branch()

    missing = await client.post(
        "/api/tickets", json={"kind": "complaint", "message": "Long wait"}, headers=auth(customer)
    )
    chosen = await client.post(
        "/api/tickets",
        json={"kind": "complaint", "message": "Long wait", "branch_id": str(branch.id)},
        headers=auth(customer),
    )

    assert missing.status_code == 400
    assert chosen.status_code == 201


async def test_customer_lists_only_own_tickets(client: AsyncClient) -> None:
    branch = await make_branch()
    mine, theirs = await make_user(), await make_user()
    for customer in (mine, theirs):
        await client.post(
            "/api/tickets",
            json={"kind": "complaint", "message": "Hello", "branch_id": str(branch.id)},
            headers=auth(customer),
        )

    response = await client.get("/api/tickets/me", headers=auth(mine))

    assert len(response.json()) == 1


@pytest.mark.guardrail
async def test_staff_see_own_branch_tickets_with_phones_masked(client: AsyncClient) -> None:
    branch, other_branch = await make_branch(), await make_branch()
    staff = await make_user(Role.STAFF, branch)
    customer = await make_user()
    for target in (branch, other_branch):
        await client.post(
            "/api/tickets",
            json={"kind": "callback", "message": "Please call", "branch_id": str(target.id)},
            headers=auth(customer),
        )

    response = await client.get(
        "/api/tickets/branch", params={"branch_id": str(other_branch.id)}, headers=auth(staff)
    )

    [ticket] = response.json()
    assert ticket["branch_id"] == str(branch.id)  # their own, whatever was asked for
    assert customer.phone not in response.text
    assert ticket["customer_phone_masked"].endswith(customer.phone[-4:])


async def test_staff_resolve_a_ticket_and_it_leaves_the_open_list(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    customer = await make_user()
    ticket_id = (
        await client.post(
            "/api/tickets",
            json={"kind": "callback", "message": "Please call", "branch_id": str(branch.id)},
            headers=auth(customer),
        )
    ).json()["id"]

    resolved = await client.put(
        f"/api/tickets/{ticket_id}/status", json={"status": "resolved"}, headers=auth(staff)
    )
    again = await client.put(
        f"/api/tickets/{ticket_id}/status", json={"status": "in_progress"}, headers=auth(staff)
    )
    open_list = await client.get("/api/tickets/branch", headers=auth(staff))
    full_list = await client.get(
        "/api/tickets/branch", params={"include_resolved": True}, headers=auth(staff)
    )

    assert resolved.json()["status"] == "resolved"
    assert again.status_code == 409
    assert open_list.json() == []
    assert len(full_list.json()) == 1


@pytest.mark.guardrail
async def test_staff_cannot_change_another_branchs_ticket(client: AsyncClient) -> None:
    branch, other_branch = await make_branch(), await make_branch()
    staff = await make_user(Role.STAFF, branch)
    ticket_id = (
        await client.post(
            "/api/tickets",
            json={"kind": "complaint", "message": "Hello", "branch_id": str(other_branch.id)},
            headers=auth(await make_user()),
        )
    ).json()["id"]

    response = await client.put(
        f"/api/tickets/{ticket_id}/status", json={"status": "resolved"}, headers=auth(staff)
    )

    assert response.status_code == 404


async def test_customer_cannot_see_branch_tickets(client: AsyncClient) -> None:
    response = await client.get("/api/tickets/branch", headers=auth(await make_user()))

    assert response.status_code == 403


@pytest.mark.parametrize("message", ["", "x" * 1001])
async def test_ticket_message_length_is_checked(client: AsyncClient, message: str) -> None:
    branch = await make_branch()

    response = await client.post(
        "/api/tickets",
        json={"kind": "complaint", "message": message, "branch_id": str(branch.id)},
        headers=auth(await make_user()),
    )

    assert response.status_code == 422
    assert await Ticket.count() == 0
