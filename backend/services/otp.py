"""Mock OTP: a random 6-digit code per phone, checked a limited number of times.

There is no SMS gateway in the demo. The code is handed back to the caller, which returns
it in the API response only when OTP_REVEAL_IN_RESPONSE is on.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta
from enum import StrEnum

from pymongo.errors import DuplicateKeyError

from config import get_settings
from models.otp_challenge import OtpChallenge
from time_utils import as_utc, now_utc

OTP_DIGITS = 6


class OtpResult(StrEnum):
    OK = "ok"
    WRONG = "wrong"
    EXPIRED = "expired"  # also: never requested
    TOO_MANY_ATTEMPTS = "too_many_attempts"


def _hash(phone: str, code: str) -> str:
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


async def issue(phone: str) -> str:
    """Make a new code for the phone, replacing any earlier one. Returns the code."""
    code = f"{secrets.randbelow(10**OTP_DIGITS):0{OTP_DIGITS}d}"
    await OtpChallenge.find(OtpChallenge.phone == phone).delete()
    try:
        await OtpChallenge(phone=phone, code_hash=_hash(phone, code)).insert()
    except DuplicateKeyError:  # two requests at once: the other one's code stands
        pass
    return code


async def check(phone: str, code: str) -> OtpResult:
    """Check a code. A correct one is used up; each wrong one costs an attempt."""
    settings = get_settings()
    challenge = await OtpChallenge.find_one(OtpChallenge.phone == phone)
    if challenge is None:
        return OtpResult.EXPIRED
    if as_utc(challenge.created_at) + timedelta(seconds=settings.otp_ttl_s) < now_utc():
        await challenge.delete()
        return OtpResult.EXPIRED
    if challenge.attempts >= settings.otp_max_attempts:
        return OtpResult.TOO_MANY_ATTEMPTS
    if hmac.compare_digest(challenge.code_hash, _hash(phone, code)):
        await challenge.delete()
        return OtpResult.OK
    challenge.attempts += 1
    await challenge.save()
    if challenge.attempts >= settings.otp_max_attempts:
        return OtpResult.TOO_MANY_ATTEMPTS
    return OtpResult.WRONG
