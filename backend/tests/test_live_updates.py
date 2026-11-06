"""Live branch updates over Socket.IO, against a real server with real Socket.IO clients."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
import socketio
import uvicorn
from httpx import AsyncClient

from auth_utils import create_access_token
from main import app
from models.branch_visit import BranchVisit
from models.user import Role, User
from sockets import BRANCH_EVENT, VISIT_EVENT
from tests.helpers import auth, make_branch, make_user, slot

TIMEOUT = 3.0
QUIET = 0.4  # how long to wait before deciding nothing was sent


@pytest.fixture
async def server_url(client: AsyncClient) -> AsyncIterator[str]:
    """The app served over real HTTP/WebSocket; shares the test's in-memory database."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="off", log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 — uvicorn exposes a flag, not an event
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task


class Listener:
    """A connected Socket.IO client that records every update of one kind it receives."""

    def __init__(self, event: str) -> None:
        self.client = socketio.AsyncClient(reconnection=False)
        self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.client.on(event, self.events.put)

    async def connect(self, url: str, user: User) -> "Listener":
        await self.client.connect(
            url, auth={"token": create_access_token(user)}, transports=["websocket"]
        )
        return self

    async def next(self) -> dict[str, Any]:
        return await asyncio.wait_for(self.events.get(), TIMEOUT)

    async def received_nothing(self) -> bool:
        await asyncio.sleep(QUIET)
        return self.events.empty()

    async def close(self) -> None:
        await self.client.disconnect()


async def _book(client: AsyncClient, customer: User, branch_id: object) -> str:
    response = await client.post(
        "/api/visits/book",
        json={"branch_id": str(branch_id), "slot_start": slot(1).isoformat()},
        headers=auth(customer),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.mark.guardrail
@pytest.mark.parametrize("auth_payload", [None, {}, {"token": "not-a-jwt"}, {"token": 12345}])
async def test_socket_without_a_valid_token_is_rejected(
    server_url: str, auth_payload: dict[str, Any] | None
) -> None:
    listener = socketio.AsyncClient(reconnection=False)

    with pytest.raises(socketio.exceptions.ConnectionError):
        await listener.connect(server_url, auth=auth_payload, transports=["websocket"])

    assert not listener.connected


async def test_staff_hear_about_a_booking_at_once(client: AsyncClient, server_url: str) -> None:
    branch = await make_branch()
    staff = await Listener(BRANCH_EVENT).connect(server_url, await make_user(Role.STAFF, branch))

    await _book(client, await make_user(), branch.id)

    update = await staff.next()
    assert update["branch_id"] == str(branch.id)
    assert set(update) == {"branch_id", "visits", "tickets"}
    await staff.close()


@pytest.mark.guardrail
async def test_staff_of_another_branch_hear_nothing(client: AsyncClient, server_url: str) -> None:
    branch, other = await make_branch(), await make_branch()
    elsewhere = await Listener(BRANCH_EVENT).connect(server_url, await make_user(Role.STAFF, other))

    await _book(client, await make_user(), branch.id)

    assert await elsewhere.received_nothing()
    await elsewhere.close()


@pytest.mark.guardrail
async def test_customers_never_receive_the_branch_queue(
    client: AsyncClient, server_url: str
) -> None:
    branch = await make_branch()
    watching = await Listener(BRANCH_EVENT).connect(server_url, await make_user())

    await _book(client, await make_user(), branch.id)

    assert await watching.received_nothing()
    await watching.close()


@pytest.mark.guardrail
async def test_the_branch_update_masks_phone_numbers(client: AsyncClient, server_url: str) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    customer = await make_user(name="Lakshmi")
    listener = await Listener(BRANCH_EVENT).connect(server_url, staff)

    await client.post("/api/visits/walk-in", json={"name": "Walk-in Ravi"}, headers=auth(staff))
    await client.post(
        "/api/tickets",
        json={"kind": "callback", "message": "Call me", "branch_id": str(branch.id)},
        headers=auth(customer),
    )

    await listener.next()
    update = await listener.next()
    assert [t["customer_name"] for t in update["tickets"]] == ["Lakshmi"]
    assert customer.phone not in str(update)
    await listener.close()


async def test_the_customer_hears_when_staff_mark_them_arrived(
    client: AsyncClient, server_url: str
) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    customer = await make_user()
    visit_id = await _book(client, customer, branch.id)
    mine = await Listener(VISIT_EVENT).connect(server_url, customer)

    await client.put(
        f"/api/visits/{visit_id}/status", json={"status": "arrived"}, headers=auth(staff)
    )

    update = await mine.next()
    assert update["id"] == visit_id and update["status"] == "arrived"
    await mine.close()


# --- walk-ins ---------------------------------------------------------------------------


async def test_staff_add_a_walk_in_who_is_already_waiting(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)

    response = await client.post(
        "/api/visits/walk-in", json={"name": "Ravi (walk-in)"}, headers=auth(staff)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["is_walk_in"] and body["status"] == "arrived"
    assert body["customer_name"] == "Ravi (walk-in)" and body["customer_phone_masked"] == ""
    today = (await client.get("/api/visits/branch", headers=auth(staff))).json()
    assert [v["id"] for v in today] == [body["id"]]


async def test_walk_ins_never_take_a_booking_slot(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    for name in ("First", "Second"):
        await client.post("/api/visits/walk-in", json={"name": name}, headers=auth(staff))

    assert await BranchVisit.count() == 2


async def test_a_walk_in_can_be_marked_valued(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)
    walk_in = (
        await client.post("/api/visits/walk-in", json={"name": "Ravi"}, headers=auth(staff))
    ).json()

    response = await client.put(
        f"/api/visits/{walk_in['id']}/status", json={"status": "valued"}, headers=auth(staff)
    )

    assert response.json()["status"] == "valued"


@pytest.mark.guardrail
@pytest.mark.parametrize("role", [Role.CUSTOMER, Role.ADMIN])
async def test_only_branch_staff_add_walk_ins(client: AsyncClient, role: Role) -> None:
    response = await client.post(
        "/api/visits/walk-in", json={"name": "Ravi"}, headers=auth(await make_user(role))
    )

    assert response.status_code == 403
