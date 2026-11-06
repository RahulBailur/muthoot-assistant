from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient, Response

from models.branch_visit import BranchVisit, VisitStatus
from models.user import Role
from tests.helpers import auth, make_branch, make_user, slot
from time_utils import today_ist


async def _book(client: AsyncClient, headers: dict[str, str], branch_id: str) -> Response:
    """Book tomorrow's first slot."""
    return await client.post(
        "/api/visits/book",
        json={"branch_id": branch_id, "slot_start": slot(1).isoformat()},
        headers=headers,
    )


async def test_availability_lists_the_branch_slots(client: AsyncClient) -> None:
    branch = await make_branch()
    customer = await make_user()
    day = (today_ist() + timedelta(days=1)).isoformat()

    response = await client.get(
        "/api/visits/availability",
        params={"date": day, "branch_id": str(branch.id)},
        headers=auth(customer),
    )

    [found] = response.json()
    assert len(found["slots"]) == 16  # 09:30–17:30 in 30-minute slots


async def test_availability_by_city_is_case_insensitive(client: AsyncClient) -> None:
    await make_branch("Kochi")
    await make_branch("Chennai")
    customer = await make_user()

    response = await client.get(
        "/api/visits/availability", params={"city": "kochi"}, headers=auth(customer)
    )

    assert [b["city"] for b in response.json()] == ["Kochi"]


async def test_city_text_cannot_act_as_a_regex(client: AsyncClient) -> None:
    await make_branch("Kochi")
    customer = await make_user()

    response = await client.get(
        "/api/visits/availability", params={"city": ".*"}, headers=auth(customer)
    )

    assert response.json() == []


async def test_book_then_slot_is_gone_and_visit_listed(client: AsyncClient) -> None:
    branch = await make_branch()
    customer = await make_user()

    booked = await _book(client, auth(customer), str(branch.id))

    assert booked.status_code == 201
    assert booked.json()["status"] == "booked"
    day = (today_ist() + timedelta(days=1)).isoformat()
    [found] = (
        await client.get(
            "/api/visits/availability",
            params={"date": day, "branch_id": str(branch.id)},
            headers=auth(customer),
        )
    ).json()
    assert len(found["slots"]) == 15
    mine = (await client.get("/api/visits/me", headers=auth(customer))).json()
    assert [v["id"] for v in mine] == [booked.json()["id"]]


async def test_same_slot_cannot_be_booked_twice(client: AsyncClient) -> None:
    branch = await make_branch()
    first, second = await make_user(), await make_user()

    await _book(client, auth(first), str(branch.id))
    response = await _book(client, auth(second), str(branch.id))

    assert response.status_code == 409


async def test_cancel_frees_the_slot(client: AsyncClient) -> None:
    branch = await make_branch()
    first, second = await make_user(), await make_user()
    visit_id = (await _book(client, auth(first), str(branch.id))).json()["id"]

    cancelled = await client.post(f"/api/visits/{visit_id}/cancel", headers=auth(first))
    rebooked = await _book(client, auth(second), str(branch.id))

    assert cancelled.json()["status"] == "cancelled"
    assert rebooked.status_code == 201


@pytest.mark.guardrail
async def test_customer_cannot_cancel_someone_elses_visit(client: AsyncClient) -> None:
    branch = await make_branch()
    owner, other = await make_user(), await make_user()
    visit_id = (await _book(client, auth(owner), str(branch.id))).json()["id"]

    response = await client.post(f"/api/visits/{visit_id}/cancel", headers=auth(other))

    assert response.status_code == 404


@pytest.mark.parametrize(
    "slot_start",
    [
        slot(-1),  # in the past
        slot(1) + timedelta(minutes=10),  # not on a slot boundary
        slot(1, index=20),  # after closing
        slot(30),  # beyond the booking window
    ],
)
async def test_book_rejects_slots_that_are_not_open(
    client: AsyncClient, slot_start: datetime
) -> None:
    branch = await make_branch()
    customer = await make_user()

    response = await client.post(
        "/api/visits/book",
        json={"branch_id": str(branch.id), "slot_start": slot_start.isoformat()},
        headers=auth(customer),
    )

    assert response.status_code == 400
    assert await BranchVisit.count() == 0


async def test_closed_weekday_has_no_slots(client: AsyncClient) -> None:
    branch = await make_branch()
    tomorrow = today_ist() + timedelta(days=1)
    branch.open_weekdays = [d for d in range(7) if d != tomorrow.weekday()]
    await branch.save()
    customer = await make_user()

    response = await _book(client, auth(customer), str(branch.id))

    assert response.status_code == 400


@pytest.mark.guardrail
@pytest.mark.parametrize("role", [Role.STAFF, Role.ADMIN])
async def test_only_customers_book(client: AsyncClient, role: Role) -> None:
    branch = await make_branch()
    user = await make_user(role, branch if role == Role.STAFF else None)

    response = await _book(client, auth(user), str(branch.id))

    assert response.status_code == 403


async def test_visit_after_an_estimate_is_a_lead(client: AsyncClient) -> None:
    branch = await make_branch()
    customer = await make_user()
    await client.post("/api/gold/estimate", json={"grams": 30}, headers=auth(customer))

    await _book(client, auth(customer), str(branch.id))

    visit = await BranchVisit.find_one()
    assert visit is not None and visit.estimate_id is not None


async def test_visit_without_an_estimate_is_not_a_lead(client: AsyncClient) -> None:
    branch = await make_branch()
    customer = await make_user()

    await _book(client, auth(customer), str(branch.id))

    visit = await BranchVisit.find_one()
    assert visit is not None and visit.estimate_id is None


async def test_staff_see_their_branch_day_with_phones_masked(client: AsyncClient) -> None:
    branch, other_branch = await make_branch(), await make_branch()
    staff = await make_user(Role.STAFF, branch)
    customer = await make_user(name="Lakshmi")
    await _book(client, auth(customer), str(branch.id))
    await _book(client, auth(await make_user()), str(other_branch.id))
    day = (today_ist() + timedelta(days=1)).isoformat()

    response = await client.get("/api/visits/branch", params={"date": day}, headers=auth(staff))

    [visit] = response.json()
    assert visit["customer_name"] == "Lakshmi"
    assert visit["customer_phone_masked"].endswith(customer.phone[-4:])
    assert customer.phone not in response.text


@pytest.mark.guardrail
async def test_staff_cannot_view_another_branch_by_passing_its_id(client: AsyncClient) -> None:
    branch, other_branch = await make_branch(), await make_branch()
    staff = await make_user(Role.STAFF, branch)
    await _book(client, auth(await make_user()), str(other_branch.id))
    day = (today_ist() + timedelta(days=1)).isoformat()

    response = await client.get(
        "/api/visits/branch",
        params={"date": day, "branch_id": str(other_branch.id)},
        headers=auth(staff),
    )

    assert response.json() == []


async def test_admin_views_any_branch_but_must_choose_one(client: AsyncClient) -> None:
    branch = await make_branch()
    admin = await make_user(Role.ADMIN)
    await _book(client, auth(await make_user()), str(branch.id))
    day = (today_ist() + timedelta(days=1)).isoformat()

    missing = await client.get("/api/visits/branch", headers=auth(admin))
    chosen = await client.get(
        "/api/visits/branch", params={"date": day, "branch_id": str(branch.id)}, headers=auth(admin)
    )

    assert missing.status_code == 400
    assert len(chosen.json()) == 1


async def test_arrived_then_valued(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    visit_id = (await _book(client, auth(await make_user()), str(branch.id))).json()["id"]

    arrived = await client.put(
        f"/api/visits/{visit_id}/status", json={"status": "arrived"}, headers=auth(staff)
    )
    valued = await client.put(
        f"/api/visits/{visit_id}/status", json={"status": "valued"}, headers=auth(staff)
    )

    assert arrived.json()["status"] == "arrived"
    assert arrived.json()["arrived_at"] is not None
    assert valued.json()["status"] == "valued"


async def test_invalid_status_change_is_refused(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    visit_id = (await _book(client, auth(await make_user()), str(branch.id))).json()["id"]

    response = await client.put(
        f"/api/visits/{visit_id}/status", json={"status": "valued"}, headers=auth(staff)
    )

    assert response.status_code == 409


async def test_arrived_visit_cannot_be_cancelled_by_customer(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    customer = await make_user()
    visit_id = (await _book(client, auth(customer), str(branch.id))).json()["id"]
    await client.put(
        f"/api/visits/{visit_id}/status", json={"status": "arrived"}, headers=auth(staff)
    )

    response = await client.post(f"/api/visits/{visit_id}/cancel", headers=auth(customer))

    assert response.status_code == 409


@pytest.mark.guardrail
async def test_staff_cannot_change_another_branchs_visit(client: AsyncClient) -> None:
    branch, other_branch = await make_branch(), await make_branch()
    staff = await make_user(Role.STAFF, branch)
    visit_id = (await _book(client, auth(await make_user()), str(other_branch.id))).json()["id"]

    response = await client.put(
        f"/api/visits/{visit_id}/status", json={"status": "arrived"}, headers=auth(staff)
    )

    assert response.status_code == 404
    visit = await BranchVisit.find_one()
    assert visit is not None and visit.status == VisitStatus.BOOKED
