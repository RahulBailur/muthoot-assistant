from datetime import datetime

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from time_utils import now_utc


class GoldRate(Document):
    """Today's 24-carat rate as set by an admin. Without one, the configured rate is used."""

    day: str  # IST date, YYYY-MM-DD
    rate_24k_per_gram: int  # rupees
    set_by: PydanticObjectId | None = None
    updated_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = "gold_rates"
        indexes = [IndexModel([("day", ASCENDING)], unique=True)]
