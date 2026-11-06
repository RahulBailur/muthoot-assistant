from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from time_utils import now_utc

# MongoDB deletes a challenge this long after it was made; the API checks the
# (shorter) configured OTP lifetime itself
OTP_DOCUMENT_TTL_SECONDS = 60 * 60


class OtpChallenge(Document):
    """A mock OTP sent to a phone. One per phone: asking again replaces it.

    Only a keyed hash of the code is stored, never the code itself.
    """

    phone: str
    code_hash: str
    attempts: int = 0
    created_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = "otp_challenges"
        indexes = [
            IndexModel([("phone", ASCENDING)], unique=True),
            IndexModel([("created_at", ASCENDING)], expireAfterSeconds=OTP_DOCUMENT_TTL_SECONDS),
        ]
