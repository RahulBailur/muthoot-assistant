from datetime import datetime

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from time_utils import now_utc

TOTAL = "total"


class VoiceUsage(Document):
    """How much of the paid speech APIs has been used: one running total.

    Counts only. No audio, no text, nothing about who spoke.
    """

    key: str = TOTAL
    stt_requests: int = 0
    stt_seconds: float = 0.0
    tts_requests: int = 0
    tts_chars: int = 0
    tts_cache_hits: int = 0  # sentences spoken again from memory, at no cost
    updated_at: datetime = Field(default_factory=now_utc)

    class Settings:
        name = "voice_usage"
        indexes = [IndexModel([("key", ASCENDING)], unique=True)]
