from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class Branch(Document):
    """A branch, with the hours its valuation slots are cut from. Seeded; public info."""

    code: str  # e.g. "KOC01"
    name: str
    city: str
    address: str
    pincode: str = Field(pattern=r"^\d{6}$")
    phone: str  # branch landline (fictional)
    open_time: str = Field(default="09:30", pattern=HHMM)  # branch local time (IST)
    close_time: str = Field(default="17:30", pattern=HHMM)
    open_weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5])  # Monday = 0
    slot_minutes: int = Field(default=30, gt=0)

    class Settings:
        name = "branches"
        indexes = [
            IndexModel([("code", ASCENDING)], unique=True),
            IndexModel([("city", ASCENDING)]),
        ]
