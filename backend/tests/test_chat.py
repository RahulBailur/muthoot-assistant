import pytest
from httpx import AsyncClient

from models.turn_analytics import TurnAnalytics
from models.user import Role
from tests.helpers import auth, make_user, otp_login


async def test_chat_needs_a_login(client: AsyncClient) -> None:
    response = await client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 401


async def test_headline_demo_over_http_after_an_otp_login(client: AsyncClient) -> None:
    token = (await otp_login(client, "9876543210", name="Asha"))["access_token"]

    response = await client.post(
        "/api/chat",
        json={"message": "Mere paas 30 gram sona hai, kitna loan milega?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "calculator"
    assert body["language"] == "hi"
    assert "₹2,47,500" in body["reply"]
    assert body["disclaimer"]
    assert body["session_id"]


async def test_session_carries_the_conversation(client: AsyncClient) -> None:
    headers = auth(await make_user())

    first = await client.post("/api/chat", json={"message": "hello"}, headers=headers)
    session = first.json()["session_id"]
    second = await client.post(
        "/api/chat", json={"message": "thanks", "session_id": session}, headers=headers
    )

    assert second.json()["session_id"] == session


@pytest.mark.parametrize("session_id", ["short", "has spaces in it", "x" * 65])
async def test_bad_session_ids_are_refused(client: AsyncClient, session_id: str) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello", "session_id": session_id},
        headers=auth(await make_user()),
    )

    assert response.status_code == 422


@pytest.mark.guardrail
async def test_shared_otp_over_http_is_blocked_and_flagged(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat", json={"message": "my otp is 482913"}, headers=auth(await make_user())
    )

    body = response.json()
    assert body["blocked"] is True
    assert body["guardrail"] == "shares_secret"
    assert "Muthoot will never ask for your OTP" in body["reply"]


async def test_every_turn_is_recorded_without_words(client: AsyncClient) -> None:
    await client.post(
        "/api/chat", json={"message": "my otp is 482913"}, headers=auth(await make_user())
    )

    [row] = await TurnAnalytics.find_all().to_list()
    assert row.pipeline == "text"
    assert row.guardrail == "shares_secret"
    assert "482913" not in row.model_dump_json()


async def test_admin_analytics_show_intents_languages_and_guardrails(client: AsyncClient) -> None:
    customer = auth(await make_user())
    for message in ("Mere paas 30 gram sona hai", "hello", "should I buy gold now?"):
        await client.post("/api/chat", json={"message": message}, headers=customer)

    response = await client.get("/api/admin/analytics", headers=auth(await make_user(Role.ADMIN)))

    assert response.status_code == 200
    body = response.json()
    assert body["turns"] == 3
    assert body["languages"] == {"en": 2, "hi": 1}
    assert body["intents"]["calculator"] == 1
    assert body["guardrails"] == {"investment_question": 1}
    assert "total_ms" in body["pipelines"]["text"]["stages"]


async def test_analytics_are_admin_only(client: AsyncClient) -> None:
    response = await client.get("/api/admin/analytics", headers=auth(await make_user()))

    assert response.status_code == 403


async def test_workflow_is_empty_without_redis(client: AsyncClient) -> None:
    response = await client.get("/api/chat/session-0001/workflow", headers=auth(await make_user()))

    assert response.json() == {"session_id": "session-0001", "events": []}
