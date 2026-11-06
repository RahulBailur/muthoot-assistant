"""Speech to text: the client's Gnani Prisma model, or a mock."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

from config import get_settings
from services import gnani, voice_usage
from services.gnani import GnaniUnavailable
from voice.audio_utils import SAMPLE_RATE, Audio, to_wav

# Words the model should expect in this domain
KEYTERMS = ["Muthoot", "gold loan", "gram", "carat", "pavan", "sovereign", "KYC", "top-up"]

# Gnani's language codes back to ours; anything else is treated as English
FROM_GNANI = {code: language for language, code in gnani.LANGUAGE_CODES.items()}


class STTUnavailable(Exception):
    """The utterance could not be transcribed."""


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str = "en"


class STTProvider(Protocol):
    name: str

    async def transcribe(self, audio: Audio) -> Transcript: ...

    def warm_up(self) -> None: ...


class MockSTT:
    """Returns a fixed transcript: the headline question. For tests and credit-free demos."""

    name = "mock"

    def __init__(
        self, text: str = "Mere paas 30 gram sona hai, kitna loan milega?", language: str = "hi"
    ) -> None:
        self.text, self.language = text, language

    async def transcribe(self, audio: Audio) -> Transcript:
        return Transcript(self.text, self.language)

    def warm_up(self) -> None:
        pass


class GnaniSTT:
    """Gnani Prisma over REST: one request per utterance (the VAD keeps them under 30 s)."""

    name = "gnani"

    def __init__(
        self,
        api_key: str,
        model: str,
        language_code: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key, self._model, self._language_code = api_key, model, language_code
        self._timeout_s, self._transport = timeout_s, transport

    def warm_up(self) -> None:
        pass

    async def transcribe(self, audio: Audio) -> Transcript:
        seconds = round(len(audio) / SAMPLE_RATE, 2)
        if reason := await voice_usage.over_cap("stt", seconds):
            raise STTUnavailable(reason)
        form = {
            "model": self._model,
            "language_code": self._language_code,
            "format": "transcribe",  # numbers as digits: "30 gram", not "thirty gram"
            "keyterms": ",".join(KEYTERMS),
        }
        try:
            response = await gnani.post(
                "/stt/v3",
                self._api_key,
                timeout_s=self._timeout_s,
                transport=self._transport,
                data=form,
                files={"audio_file": ("speech.wav", to_wav(audio), "audio/wav")},
            )
        except GnaniUnavailable as error:
            raise STTUnavailable(str(error)) from error
        await voice_usage.record("stt", seconds)
        try:
            body = response.json()
            text = str(body.get("transcript") or "").strip()
            language = FROM_GNANI.get(str(body.get("detected_language_code")), "en")
        except (ValueError, AttributeError) as error:
            raise STTUnavailable("Gnani STT returned no usable transcript") from error
        return Transcript(text, language)


@lru_cache
def get_stt() -> STTProvider:
    settings = get_settings()
    if settings.stt_provider == "gnani":
        return GnaniSTT(
            settings.gnani_api_key,
            settings.gnani_stt_model,
            settings.gnani_stt_language,
            settings.gnani_timeout_s,
        )
    return MockSTT()
