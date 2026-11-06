from datetime import timedelta

import jwt
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from auth_utils import JWT_ALGORITHM
from config import Settings, get_settings
from models.otp_challenge import OtpChallenge
from models.user import Role, User
from rate_limit import limiter
from tests.helpers import STAFF_PASSWORD, auth, make_branch, make_user, otp_login
from time_utils import now_utc

PHONE = "9876543210"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_otp_login_creates_customer_and_returns_working_token(client: AsyncClient) -> None:
    body = await otp_login(client, PHONE, name="Asha")

    assert body["user"]["role"] == "customer"
    assert body["user"]["name"] == "Asha"
    me = await client.get("/api/auth/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["id"] == body["user"]["id"]


async def test_otp_login_finds_existing_customer(client: AsyncClient) -> None:
    customer = await make_user(Role.CUSTOMER, name="Existing")

    body = await otp_login(client, customer.phone, name="Someone Else")

    assert body["user"]["id"] == str(customer.id)
    assert body["user"]["name"] == "Existing"
    assert await User.count() == 1


@pytest.mark.guardrail
async def test_phone_is_masked_in_every_auth_response(client: AsyncClient) -> None:
    sent = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    assert sent.json()["sent_to"] == "******3210"

    body = await otp_login(client, PHONE)
    assert PHONE not in str(body)
    me = await client.get("/api/auth/me", headers=_bearer(body["access_token"]))
    assert PHONE not in me.text
    assert me.json()["phone_masked"] == "******3210"


@pytest.mark.guardrail
async def test_otp_is_stored_hashed(client: AsyncClient) -> None:
    sent = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    code = sent.json()["demo_otp"]

    challenge = await OtpChallenge.find_one(OtpChallenge.phone == PHONE)
    assert challenge is not None
    assert code not in challenge.code_hash


async def test_wrong_otp_is_rejected(client: AsyncClient) -> None:
    sent = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    wrong = "000000" if sent.json()["demo_otp"] != "000000" else "111111"

    response = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "otp": wrong})

    assert response.status_code == 401
    assert await User.count() == 0


@pytest.mark.guardrail
async def test_otp_locks_after_max_attempts_even_with_the_right_code(client: AsyncClient) -> None:
    sent = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    code = sent.json()["demo_otp"]
    wrong = "000000" if code != "000000" else "111111"

    statuses = []
    for _ in range(get_settings().otp_max_attempts):
        response = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "otp": wrong})
        statuses.append(response.status_code)
    right = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "otp": code})

    assert statuses[-1] == 429
    assert right.status_code == 429


async def test_otp_works_only_once(client: AsyncClient) -> None:
    sent = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    code = sent.json()["demo_otp"]

    first = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "otp": code})
    second = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "otp": code})

    assert first.status_code == 200
    assert second.status_code == 401


async def test_expired_otp_is_rejected(client: AsyncClient) -> None:
    sent = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    challenge = await OtpChallenge.find_one(OtpChallenge.phone == PHONE)
    assert challenge is not None
    challenge.created_at = now_utc() - timedelta(seconds=get_settings().otp_ttl_s + 1)
    await challenge.save()

    response = await client.post(
        "/api/auth/otp/verify", json={"phone": PHONE, "otp": sent.json()["demo_otp"]}
    )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


async def test_new_otp_replaces_the_old_one(client: AsyncClient) -> None:
    first = (await client.post("/api/auth/otp/request", json={"phone": PHONE})).json()["demo_otp"]
    second = (await client.post("/api/auth/otp/request", json={"phone": PHONE})).json()["demo_otp"]

    assert await OtpChallenge.count() == 1
    if first != second:
        old = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "otp": first})
        assert old.status_code == 401
    new = await client.post("/api/auth/otp/verify", json={"phone": PHONE, "otp": second})
    assert new.status_code == 200


async def test_otp_is_hidden_when_reveal_is_off(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "otp_reveal_in_response", False)

    response = await client.post("/api/auth/otp/request", json={"phone": PHONE})

    assert response.status_code == 200
    assert response.json()["demo_otp"] is None


@pytest.mark.parametrize("phone", ["12345", "1234567890", "98765432100", "98765abcde"])
async def test_otp_request_rejects_invalid_indian_phone(client: AsyncClient, phone: str) -> None:
    response = await client.post("/api/auth/otp/request", json={"phone": phone})

    assert response.status_code == 422


@pytest.mark.guardrail
@pytest.mark.parametrize("role", ["staff", "admin"])
async def test_otp_login_never_grants_staff_or_admin(client: AsyncClient, role: str) -> None:
    sent = await client.post("/api/auth/otp/request", json={"phone": PHONE})
    response = await client.post(
        "/api/auth/otp/verify",
        json={"phone": PHONE, "otp": sent.json()["demo_otp"], "role": role},
    )

    assert response.json()["user"]["role"] == "customer"
    user = await User.find_one(User.phone == PHONE)
    assert user is not None and user.role == Role.CUSTOMER


@pytest.mark.guardrail
async def test_staff_cannot_log_in_with_an_otp(client: AsyncClient) -> None:
    staff = await make_user(Role.STAFF, await make_branch())
    sent = await client.post("/api/auth/otp/request", json={"phone": staff.phone})

    response = await client.post(
        "/api/auth/otp/verify", json={"phone": staff.phone, "otp": sent.json()["demo_otp"]}
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", [Role.STAFF, Role.ADMIN])
async def test_staff_and_admin_log_in_with_password(client: AsyncClient, role: Role) -> None:
    user = await make_user(role, await make_branch() if role == Role.STAFF else None)

    response = await client.post(
        "/api/auth/login", json={"phone": user.phone, "password": STAFF_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == role.value


@pytest.mark.parametrize("password", ["wrong-password", ""])
async def test_staff_login_rejects_wrong_password(client: AsyncClient, password: str) -> None:
    staff = await make_user(Role.STAFF, await make_branch())

    response = await client.post(
        "/api/auth/login", json={"phone": staff.phone, "password": password}
    )

    assert response.status_code == 401


@pytest.mark.guardrail
async def test_customer_cannot_use_the_password_login(client: AsyncClient) -> None:
    customer = await make_user(Role.CUSTOMER)

    response = await client.post(
        "/api/auth/login", json={"phone": customer.phone, "password": "anything-at-all"}
    )

    assert response.status_code == 401


async def test_unknown_phone_and_wrong_password_look_the_same(client: AsyncClient) -> None:
    staff = await make_user(Role.STAFF, await make_branch())

    unknown = await client.post("/api/auth/login", json={"phone": PHONE, "password": "x" * 10})
    wrong = await client.post("/api/auth/login", json={"phone": staff.phone, "password": "x" * 10})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


@pytest.mark.guardrail
async def test_role_comes_from_the_database_not_the_token(client: AsyncClient) -> None:
    customer = await make_user(Role.CUSTOMER)
    settings = get_settings()
    forged = jwt.encode(
        {"sub": str(customer.id), "role": "admin", "exp": now_utc() + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
    )

    response = await client.get("/api/admin/stats", headers=_bearer(forged))

    assert response.status_code == 403


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        jwt.encode({"sub": "x"}, "some-other-secret-that-is-long-enough", algorithm="HS256"),
    ],
)
async def test_bad_tokens_are_rejected(client: AsyncClient, token: str) -> None:
    response = await client.get("/api/auth/me", headers=_bearer(token))

    assert response.status_code == 401


async def test_expired_token_is_rejected(client: AsyncClient) -> None:
    customer = await make_user(Role.CUSTOMER)
    expired = jwt.encode(
        {"sub": str(customer.id), "exp": now_utc() - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm=JWT_ALGORITHM,
    )

    response = await client.get("/api/auth/me", headers=_bearer(expired))

    assert response.status_code == 401


async def test_me_works_for_staff_and_shows_branch(client: AsyncClient) -> None:
    branch = await make_branch()
    staff = await make_user(Role.STAFF, branch)

    response = await client.get("/api/auth/me", headers=auth(staff))

    assert response.json()["branch_id"] == str(branch.id)


async def test_auth_routes_are_rate_limited(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_auth", "3/minute")
    limiter.reset()

    statuses = [
        (await client.post("/api/auth/otp/request", json={"phone": PHONE})).status_code
        for _ in range(4)
    ]

    assert statuses == [200, 200, 200, 429]


def test_mock_db_is_refused_outside_tests() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="development", use_mock_db=True, jwt_secret="x" * 40)


def test_placeholder_jwt_secret_is_refused_for_the_demo() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="demo", use_mock_db=False, jwt_secret="change-me-to-a-long-random-string"
        )
