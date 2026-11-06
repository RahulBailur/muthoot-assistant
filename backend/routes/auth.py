import asyncio
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, StringConstraints
from pymongo.errors import DuplicateKeyError

from auth_utils import CurrentUser, create_access_token, hash_password, verify_password
from config import get_settings
from models.user import Role, User
from privacy import mask_phone
from rate_limit import auth_limit, limiter
from services import otp
from services.otp import OtpResult

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Indian mobile number: 10 digits, starting 6–9
IndianPhone = Annotated[str, StringConstraints(pattern=r"^[6-9]\d{9}$")]
OtpCode = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]

OTP_ERRORS = {
    OtpResult.WRONG: (status.HTTP_401_UNAUTHORIZED, "Incorrect OTP"),
    OtpResult.EXPIRED: (status.HTTP_401_UNAUTHORIZED, "OTP expired. Please request a new one"),
    OtpResult.TOO_MANY_ATTEMPTS: (
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many wrong attempts. Please request a new OTP",
    ),
}


@lru_cache
def _dummy_hash() -> str:
    """Compared against when the phone is unknown, so timing doesn't reveal which exist."""
    return hash_password("no-such-user")


class OtpRequest(BaseModel):
    phone: IndianPhone


class OtpSent(BaseModel):
    sent_to: str  # masked
    expires_in_s: int
    # Only while OTP_REVEAL_IN_RESPONSE is on: the demo has no SMS gateway
    demo_otp: str | None = None


class OtpVerifyRequest(BaseModel):
    """Logs a customer in. There is no role field: any `role` sent by a client is ignored."""

    phone: IndianPhone
    otp: OtpCode
    # Used only when this phone has no account yet
    name: str | None = Field(default=None, min_length=2, max_length=80)


class StaffLoginRequest(BaseModel):
    phone: IndianPhone
    password: str


class UserOut(BaseModel):
    id: str
    name: str
    phone_masked: str
    role: Role
    branch_id: str | None = None
    preferred_language: str

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=str(user.id),
            name=user.name,
            phone_masked=mask_phone(user.phone),
            role=user.role,
            branch_id=str(user.branch_id) if user.branch_id else None,
            preferred_language=user.preferred_language,
        )


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    user: UserOut


@router.post("/otp/request")
@limiter.limit(auth_limit)
async def request_otp(request: Request, body: OtpRequest) -> OtpSent:
    """Send a mock OTP. Same answer whether or not the phone has an account."""
    settings = get_settings()
    code = await otp.issue(body.phone)
    return OtpSent(
        sent_to=mask_phone(body.phone),
        expires_in_s=settings.otp_ttl_s,
        demo_otp=code if settings.otp_reveal_in_response else None,
    )


@router.post("/otp/verify")
@limiter.limit(auth_limit)
async def verify_otp(request: Request, body: OtpVerifyRequest) -> AuthResponse:
    """Customer login. A phone seen for the first time gets a new customer account."""
    result = await otp.check(body.phone, body.otp)
    if result != OtpResult.OK:
        code, detail = OTP_ERRORS[result]
        raise HTTPException(status_code=code, detail=detail)
    user = await User.find_one(User.phone == body.phone)
    if user is None:
        user = User(name=(body.name or "Customer").strip(), phone=body.phone, role=Role.CUSTOMER)
        try:
            await user.insert()
        except DuplicateKeyError:  # created by a parallel request a moment ago
            user = await User.find_one(User.phone == body.phone)
    if user is None or user.role != Role.CUSTOMER:
        # Staff and admin log in with their password, never with an OTP
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please log in with your staff password")
    return AuthResponse(access_token=create_access_token(user), user=UserOut.from_user(user))


@router.post("/login")
@limiter.limit(auth_limit)
async def staff_login(request: Request, body: StaffLoginRequest) -> AuthResponse:
    """Branch staff and admin login."""
    user = await User.find_one(User.phone == body.phone)
    stored = user.password_hash if user and user.password_hash else None
    password_ok = await asyncio.to_thread(verify_password, body.password, stored or _dummy_hash())
    if user is None or stored is None or user.role == Role.CUSTOMER or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid phone or password")
    return AuthResponse(access_token=create_access_token(user), user=UserOut.from_user(user))


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.from_user(user)
