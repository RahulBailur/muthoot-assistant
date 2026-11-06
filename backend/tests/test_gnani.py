"""The Gnani STT and TTS clients against a fake HTTP server: no credits are spent here."""

import asyncio
import io
import json
import wave
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import httpx
import numpy as np
import pytest
from httpx import AsyncClient

from config import get_settings
from models.user import Role
from models.voice_usage import VoiceUsage
from services import gnani, voice_usage
from services.stt import GnaniSTT, STTUnavailable
from services.tts import CachedTTS, GnaniTTS, TTSUnavailable
from tests.helpers import auth, make_user

KEY = "test-gnani-key"
Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


@pytest.fixture(autouse=True)
def fresh_credit_flag() -> Iterator[None]:
    gnani.reset_credit_flag()
    yield
    gnani.reset_credit_flag()


def wav_bytes(rate: int = 24_000, seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x01\x00" * int(rate * seconds))
    return buffer.getvalue()


def stt(handler: Handler, key: str = KEY) -> GnaniSTT:
    return GnaniSTT(key, "prisma-v3.0", "indic-auto", 5.0, httpx.MockTransport(handler))


def tts(handler: Handler, key: str = KEY) -> GnaniTTS:
    return GnaniTTS(key, "timbre-v3.0", "Lakshmi", 24_000, 5.0, httpx.MockTransport(handler))


def one_second() -> Any:
    return np.zeros(16_000, dtype=np.float32)


def transcript(text: str, language: str = "hi-IN") -> httpx.Response:
    return httpx.Response(
        200, json={"success": True, "transcript": text, "detected_language_code": language}
    )


def no_request() -> Handler:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made")

    return handler


# --- STT --------------------------------------------------------------------------------


async def test_stt_sends_the_key_as_a_header_and_the_audio_as_a_wav(client: AsyncClient) -> None:
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key-ID")
        seen["body"] = request.content
        return transcript("मेरे पास 30 ग्राम सोना है")

    result = await stt(handler).transcribe(one_second())

    assert seen["url"] == "https://api.vachana.ai/stt/v3"
    assert seen["key"] == KEY and KEY not in seen["url"]
    for field in (b'name="model"', b"prisma-v3.0", b"indic-auto", b'name="format"', b"RIFF"):
        assert field in seen["body"]
    assert result.text == "मेरे पास 30 ग्राम सोना है" and result.language == "hi"


@pytest.mark.parametrize(("code", "language"), [("ml-IN", "ml"), ("ta-IN", "ta"), ("te-IN", "en")])
async def test_stt_maps_the_detected_language(
    client: AsyncClient, code: str, language: str
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return transcript("x", code)

    assert (await stt(handler).transcribe(one_second())).language == language


async def test_stt_counts_the_seconds_it_used(client: AsyncClient) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return transcript("hello", "en-IN")

    await stt(handler).transcribe(one_second())

    usage = await voice_usage.current()
    assert usage.stt_requests == 1 and usage.stt_seconds == pytest.approx(1.0)


@pytest.mark.parametrize("status", [400, 401, 500])
async def test_stt_failures_never_include_the_key_or_body(client: AsyncClient, status: int) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=f"bad request with {KEY}")

    with pytest.raises(STTUnavailable) as raised:
        await stt(handler).transcribe(one_second())

    assert KEY not in str(raised.value) and str(status) in str(raised.value)
    assert (await voice_usage.current()).stt_requests == 0


async def test_without_a_key_no_request_is_made(client: AsyncClient) -> None:
    with pytest.raises(STTUnavailable):
        await stt(no_request(), key="").transcribe(one_second())
    with pytest.raises(TTSUnavailable):
        await tts(no_request(), key="").synthesize("hello")


# --- credits ----------------------------------------------------------------------------


async def test_a_busy_key_is_retried_once(client: AsyncClient) -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else transcript("ok")

    assert (await stt(handler).transcribe(one_second())).text == "ok"
    assert len(calls) == 2


async def test_out_of_credit_stops_all_calls(client: AsyncClient) -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(402, json={"detail": {"error_code": "INSUFFICIENT_CREDIT"}})

    with pytest.raises(TTSUnavailable, match="credits"):
        await tts(handler).synthesize("hello")
    with pytest.raises(STTUnavailable, match="credits"):
        await stt(handler).transcribe(one_second())

    assert len(calls) == 1  # the second call never left the server
    assert gnani.out_of_credit()


async def test_past_the_tts_cap_no_request_is_made(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "voice_max_tts_chars", 10)
    await VoiceUsage(tts_chars=8).insert()

    with pytest.raises(TTSUnavailable, match="cap reached"):
        await tts(no_request()).synthesize("this is too long")


async def test_past_the_stt_cap_no_request_is_made(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "voice_max_stt_seconds", 60)
    await VoiceUsage(stt_seconds=59.5).insert()

    with pytest.raises(STTUnavailable, match="cap reached"):
        await stt(no_request()).transcribe(one_second())


async def test_only_one_request_is_ever_in_flight(client: AsyncClient) -> None:
    in_flight, most = 0, 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, most
        in_flight += 1
        most = max(most, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})

    speaker = tts(handler)
    await asyncio.gather(*(speaker.synthesize(f"sentence {n}") for n in range(4)))

    assert most == 1


# --- TTS --------------------------------------------------------------------------------


async def test_tts_asks_for_the_voice_language_and_a_wav(client: AsyncClient) -> None:
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-API-Key-ID")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})

    speech = await tts(handler).synthesize("നമസ്കാരം", "ml")

    assert seen["url"] == "https://api.vachana.ai/api/v1/tts/inference"
    assert seen["key"] == KEY
    body = seen["body"]
    assert body["text"] == "നമസ്കാരം" and body["language"] == "ml-IN"
    assert body["model"] == "timbre-v3.0" and body["voice"] == "Lakshmi"
    assert body["audio_config"]["container"] == "wav"
    assert speech.sample_rate == 24_000 and speech.seconds == pytest.approx(1.0)
    usage = await voice_usage.current()
    assert usage.tts_requests == 1 and usage.tts_chars == len("നമസ്കാരം")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text=f"error {KEY}"),
        httpx.Response(200, content=b"", headers={"content-type": "audio/wav"}),
        httpx.Response(200, content=b"RIFFbroken", headers={"content-type": "audio/wav"}),
    ],
)
async def test_tts_failures_become_tts_unavailable(
    client: AsyncClient, response: httpx.Response
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(TTSUnavailable) as raised:
        await tts(handler).synthesize("hello")

    assert KEY not in str(raised.value)


async def test_a_repeated_sentence_is_spoken_from_memory(client: AsyncClient) -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["text"])
        return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})

    cached = CachedTTS(tts(handler), entries=10)
    first = await cached.synthesize("This is an estimate only.", "en")
    again = await cached.synthesize("This is  an estimate only.", "en")  # spacing differs
    other_language = await cached.synthesize("This is an estimate only.", "hi")

    assert again == first and other_language.pcm16
    assert len(calls) == 2  # English once, Hindi once
    assert (await voice_usage.current()).tts_cache_hits == 1


async def test_the_cache_forgets_the_oldest_sentence(client: AsyncClient) -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content)["text"])
        return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})

    cached = CachedTTS(tts(handler), entries=2)
    for text in ("one", "two", "three", "one"):
        await cached.synthesize(text)

    assert calls == ["one", "two", "three", "one"]


# --- admin view -------------------------------------------------------------------------


async def test_admin_sees_voice_usage_against_the_caps(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "voice_max_tts_chars", 5000)
    await voice_usage.record("tts", 42)
    await voice_usage.record("stt", 2.5)

    response = await client.get("/api/admin/voice-usage", headers=auth(await make_user(Role.ADMIN)))

    body = response.json()
    assert body["tts_chars"] == 42 and body["stt_seconds"] == 2.5
    assert body["caps"] == {"stt_seconds": None, "tts_chars": 5000}
    assert body["out_of_credit"] is False


async def test_voice_usage_is_admin_only(client: AsyncClient) -> None:
    response = await client.get("/api/admin/voice-usage", headers=auth(await make_user()))

    assert response.status_code == 403
