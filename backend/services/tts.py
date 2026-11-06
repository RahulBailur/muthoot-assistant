"""Text to speech: the client's Gnani Timbre model behind an in-memory cache, or a mock.

Fixed sentences (the OTP warning, the estimate disclaimer, greetings) come round again and
again; once spoken, they are replayed from memory and cost no credits. Audio is never
written to disk.
"""

import logging
import wave
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from config import get_settings
from services import gnani, voice_usage
from services.gnani import GnaniUnavailable
from voice.audio_utils import decode_speech

logger = logging.getLogger(__name__)


class TTSUnavailable(Exception):
    """This text could not be spoken. The reply is still shown as text."""


@dataclass(frozen=True)
class Speech:
    pcm16: bytes  # mono, little-endian
    sample_rate: int
    provider: str = ""

    @property
    def seconds(self) -> float:
        return len(self.pcm16) / 2 / self.sample_rate


class TTSProvider(Protocol):
    name: str

    async def synthesize(self, text: str, language: str = "en") -> Speech: ...

    def warm_up(self) -> None: ...


class MockTTS:
    """Silence, 50 ms per character. For tests and for running without a TTS model."""

    name = "mock"
    sample_rate = 24_000

    async def synthesize(self, text: str, language: str = "en") -> Speech:
        samples = int(self.sample_rate * 0.05 * max(1, len(text)))
        return Speech(b"\x00\x00" * samples, self.sample_rate, self.name)

    def warm_up(self) -> None:
        pass


class GnaniTTS:
    """Gnani Timbre over REST. A timbre-v3.0 voice speaks every one of our languages, and
    reads ₹ amounts with Indian grouping ("two lakh forty-seven thousand rupees") itself."""

    name = "gnani"

    def __init__(
        self,
        api_key: str,
        model: str,
        voice: str,
        sample_rate: int,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key, self._model, self._voice = api_key, model, voice
        self._sample_rate, self._timeout_s, self._transport = sample_rate, timeout_s, transport

    def warm_up(self) -> None:
        pass

    async def synthesize(self, text: str, language: str = "en") -> Speech:
        if reason := await voice_usage.over_cap("tts", len(text)):
            raise TTSUnavailable(reason)
        body = {
            "text": text,
            "model": self._model,
            "voice": self._voice,
            "language": gnani.LANGUAGE_CODES.get(language, "en-IN"),
            "audio_config": {
                "sample_rate": self._sample_rate,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        try:
            response = await gnani.post(
                "/api/v1/tts/inference",
                self._api_key,
                timeout_s=self._timeout_s,
                transport=self._transport,
                json=body,
            )
        except GnaniUnavailable as error:
            raise TTSUnavailable(str(error)) from error
        await voice_usage.record("tts", len(text))
        try:
            pcm16, rate = decode_speech(response.content, response.headers.get("content-type", ""))
        except (ValueError, EOFError, wave.Error) as error:
            raise TTSUnavailable("Gnani TTS returned audio that could not be read") from error
        if not pcm16:
            raise TTSUnavailable("Gnani TTS returned empty audio")
        return Speech(pcm16, rate, self.name)


class CachedTTS:
    """Remembers the last `entries` sentences spoken, per language."""

    def __init__(self, provider: TTSProvider, entries: int) -> None:
        self._provider, self._entries = provider, entries
        self._cache: OrderedDict[tuple[str, str], Speech] = OrderedDict()
        self.name = provider.name

    def warm_up(self) -> None:
        self._provider.warm_up()

    async def synthesize(self, text: str, language: str = "en") -> Speech:
        key = (language, " ".join(text.split()))
        if (speech := self._cache.get(key)) is not None:
            self._cache.move_to_end(key)
            try:
                await voice_usage.record_cache_hit()
            except Exception:  # noqa: BLE001 — counting must never cost the customer a reply
                logger.warning("Could not count a TTS cache hit")
            return speech
        speech = await self._provider.synthesize(text, language)
        if self._entries > 0:
            self._cache[key] = speech
            while len(self._cache) > self._entries:
                self._cache.popitem(last=False)
        return speech


@lru_cache
def get_tts() -> TTSProvider:
    settings = get_settings()
    if settings.tts_provider == "mock":
        return MockTTS()
    gnani_tts = GnaniTTS(
        settings.gnani_api_key,
        settings.gnani_tts_model,
        settings.gnani_tts_voice,
        settings.gnani_tts_sample_rate,
        settings.gnani_timeout_s,
    )
    return CachedTTS(gnani_tts, settings.tts_cache_entries)
