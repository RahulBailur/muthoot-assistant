from datetime import datetime
from enum import StrEnum

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from time_utils import now_utc


class Role(StrEnum):
    CUSTOMER = "customer"
    STAFF = "staff"  # branch staff
    ADMIN = "admin"


class User(Document):
    name: str
    phone: str  # 10-digit Indian mobile; shown and spoken masked only
    role: Role = Role.CUSTOMER
    # Staff and admin log in with a password. Customers log in with a mock OTP and have none.
    password_hash: str | None = None
    branch_id: PydanticObjectId | None = None  # staff only: the branch they work at
    preferred_language: str = "en"
    created_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = "users"
        indexes = [IndexModel([("phone", ASCENDING)], unique=True)]
