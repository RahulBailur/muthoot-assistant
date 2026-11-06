"""The paid speech API's running total, and the caps that keep the free credits from running dry.

Checked before each Gnani call and added to after it. Past a cap, STT and TTS refuse, and the
voice pipeline carries on as text: the reply is still shown, just not spoken.
"""

from typing import Literal

from config import get_settings
from models.voice_usage import TOTAL, VoiceUsage
from time_utils import now_utc

Kind = Literal["stt", "tts"]


async def current() -> VoiceUsage:
    return await VoiceUsage.find_one(VoiceUsage.key == TOTAL) or VoiceUsage()


async def over_cap(kind: Kind, amount: float) -> str | None:
    """Why this call must not be made, or None. `amount` is seconds (STT) or characters (TTS)."""
    settings = get_settings()
    cap = settings.voice_max_stt_seconds if kind == "stt" else settings.voice_max_tts_chars
    if cap <= 0:
        return None
    usage = await current()
    used = usage.stt_seconds if kind == "stt" else usage.tts_chars
    if used + amount > cap:
        unit = "seconds" if kind == "stt" else "characters"
        return f"voice {kind.upper()} cap reached ({used:g} of {cap} {unit} used)"
    return None


async def record(kind: Kind, amount: float) -> None:
    """Add one call to the running total."""
    if kind == "stt":
        await _add({"stt_requests": 1, "stt_seconds": amount})
    else:
        await _add({"tts_requests": 1, "tts_chars": int(amount)})


async def record_cache_hit() -> None:
    await _add({"tts_cache_hits": 1})


async def _add(change: dict[str, float]) -> None:
    """One atomic increment, creating the total on first use."""
    await VoiceUsage.get_motor_collection().update_one(
        {"key": TOTAL}, {"$inc": change, "$set": {"updated_at": now_utc()}}, upsert=True
    )
