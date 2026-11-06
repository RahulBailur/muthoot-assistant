"""The voice pipeline with stand-in speech models: detection, turn flow, barge-in, timings."""

import asyncio
import io
import wave
from typing import Any

import numpy as np
import pytest
from httpx import AsyncClient

from agents.intent_classifier import IntentClassifier
from agents.languages import ESTIMATE_DISCLAIMER, SAFE_FALLBACK
from models.turn_analytics import TurnAnalytics
from services.llm import MockLLM
from services.tts import MockTTS
from tests.helpers import make_user
from tests.llm_helpers import ScriptedLLM
from tests.voice_helpers import UTTERANCE, FakeSTT, FakeTTS, Wire, frames, silence, tone
from voice import cascade_pipeline
from voice.audio_utils import (
    FRAME_MS,
    FRAME_SAMPLES,
    Framer,
    decode_speech,
    float_to_pcm16,
    pcm16_to_float,
    resample,
    to_wav,
)
from voice.cascade_pipeline import VoiceSession, VoiceState, shorten_first, split_sentences
from voice.timing import TurnTimer
from voice.vad import SpeechDetector, VADConfig, energy_vad

CONFIG = VADConfig(min_speech_ms=96, silence_ms=200, pre_roll_ms=96, max_utterance_s=2)

# --- audio helpers ----------------------------------------------------------------------


def test_pcm_round_trip_is_lossless_to_one_step() -> None:
    audio = np.array([0.0, 0.5, -0.5, 0.999, -1.0], dtype=np.float32)

    assert np.allclose(pcm16_to_float(float_to_pcm16(audio)), audio, atol=1 / 32000)


def test_out_of_range_samples_are_clipped_not_wrapped() -> None:
    assert pcm16_to_float(float_to_pcm16(np.array([2.0, -2.0], dtype=np.float32))).tolist() == [
        pytest.approx(1.0, abs=1e-3),
        pytest.approx(-1.0, abs=1e-3),
    ]


@pytest.mark.parametrize(
    ("source", "target"), [(24_000, 16_000), (16_000, 8_000), (16_000, 16_000)]
)
def test_resampling_changes_the_length_in_proportion(source: int, target: int) -> None:
    audio = np.zeros(source, dtype=np.float32)

    assert len(resample(audio, source, target)) == target


def test_framer_cuts_any_chunking_into_whole_frames() -> None:
    data = tone(5 * FRAME_MS)
    framer = Framer()

    got = [
        frame
        for start in range(0, len(data), 333)
        for frame in framer.push(data[start : start + 333])
    ]

    assert len(got) == 5 and all(len(frame) == FRAME_SAMPLES for frame in got)
    assert np.allclose(np.concatenate(got), pcm16_to_float(data))


def test_a_wav_payload_is_decoded_with_its_own_sample_rate() -> None:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22_050)
        wav.writeframes(b"\x01\x00" * 10)

    assert decode_speech(buffer.getvalue(), "audio/wav") == (b"\x01\x00" * 10, 22_050)


def test_an_utterance_becomes_a_16_khz_wav_in_memory() -> None:
    audio = pcm16_to_float(tone(320))

    pcm16, rate = decode_speech(to_wav(audio), "audio/wav")

    assert rate == 16_000 and pcm16 == float_to_pcm16(audio)


# --- sentences --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("One short reply.", ["One short reply."]),
        (
            "Your visit is booked for Monday at 10 AM. Please bring a photo ID with you.",
            ["Your visit is booked for Monday at 10 AM.", "Please bring a photo ID with you."],
        ),
        (
            "You could get about Rs. 2,22,700 to Rs. 2,47,500 today. It is only an estimate.",
            ["You could get about Rs. 2,22,700 to Rs. 2,47,500 today. It is only an estimate."],
        ),
        (
            "Yes. Bring one photo ID and one address proof.",
            ["Yes. Bring one photo ID and one address proof."],
        ),
        (
            "आपको लगभग ₹2,22,700 से ₹2,47,500 तक का लोन मिल सकता है। क्या मैं शाखा विज़िट बुक कर दूँ?",
            [
                "आपको लगभग ₹2,22,700 से ₹2,47,500 तक का लोन मिल सकता है।",
                "क्या मैं शाखा विज़िट बुक कर दूँ?",
            ],
        ),
    ],
)
def test_split_sentences(text: str, expected: list[str]) -> None:
    assert split_sentences(text) == expected


# --- detector ---------------------------------------------------------------------------


def run_detector(data: bytes, config: VADConfig = CONFIG) -> list[Any]:
    detector = SpeechDetector(energy_vad(), config)
    return [event for frame in frames(data) if (event := detector.feed(frame))]


def test_silence_never_starts_an_utterance() -> None:
    assert run_detector(silence(2000)) == []


def test_a_blip_shorter_than_the_minimum_is_ignored() -> None:
    assert run_detector(silence(6 * FRAME_MS) + tone(2 * FRAME_MS) + silence(640)) == []


def test_speech_then_silence_gives_start_and_end() -> None:
    events = run_detector(silence(300) + tone(15 * FRAME_MS) + silence(400))

    assert [event.kind for event in events] == ["start", "end"]


def test_a_pause_shorter_than_the_silence_window_does_not_end_it() -> None:
    data = tone(10 * FRAME_MS) + silence(3 * FRAME_MS) + tone(10 * FRAME_MS) + silence(400)

    assert [event.kind for event in run_detector(data)] == ["start", "end"]


def test_an_utterance_is_cut_off_at_the_maximum_length() -> None:
    events = run_detector(tone(3000))

    assert [event.kind for event in events][:2] == ["start", "end"]
    assert events[1].audio is not None and len(events[1].audio) <= 2.1 * 16_000


def test_two_utterances_in_a_row_are_both_detected() -> None:
    data = (tone(10 * FRAME_MS) + silence(400)) * 2

    assert [event.kind for event in run_detector(data)] == ["start", "end", "start", "end"]


# --- timer ------------------------------------------------------------------------------


def test_stage_timings_are_differences_between_marks() -> None:
    now = [10.0]
    timer = TurnTimer(10.0, lambda: now[0])
    for name, at in [
        ("vad_end", 10.5),
        ("transcript", 11.5),
        ("routed", 11.6),
        ("reply", 12.6),
        ("first_audio", 13.1),
        ("last_audio", 14.0),
    ]:
        now[0] = at
        timer.mark(name)

    assert timer.stages() == {
        "end_of_speech_ms": 500.0,
        "stt_ms": 1000.0,
        "routing_ms": 100.0,
        "llm_ms": 1000.0,
        "tts_first_chunk_ms": 500.0,
        "ttfa_ms": 3100.0,
        "total_ms": 4000.0,
    }


# --- a session --------------------------------------------------------------------------


class Rig:
    """A VoiceSession wired to stand-ins, with everything it sends collected."""

    def __init__(self, user: Any, llm: Any = None, chunking: str = "sentence") -> None:
        self.wire, self.stt, self.tts = Wire(), FakeSTT(), FakeTTS()
        self.session = VoiceSession(
            user,
            "voice-session-1",
            self.wire.send_json,
            self.wire.send_audio,
            stt=self.stt,
            tts=self.tts,
            probability=energy_vad(),
            vad_config=CONFIG,
            chunking=chunking,
            llm=llm or MockLLM(),
            classifier=IntentClassifier(),
        )

    async def speak(self, wait: bool = True) -> None:
        await self.session.receive_audio(UTTERANCE)
        if wait and self.session._turn is not None:
            await self.session._turn


@pytest.fixture
async def rig(client: AsyncClient) -> Rig:
    return Rig(await make_user())


async def test_the_headline_question_spoken_gets_a_spoken_estimate(rig: Rig) -> None:
    await rig.session.start()
    await rig.speak()

    assert (
        rig.wire.states
        == (
            "IDLE LISTENING TRANSCRIBING THINKING TOOL_EXECUTION GENERATING_RESPONSE SPEAKING"
        ).split()
    )
    assert rig.wire.of("transcript")[0]["text"].startswith("Mere paas 30 gram")
    reply = rig.wire.of("reply")[0]
    assert reply["intent"] == "calculator" and reply["language"] == "hi"
    assert "₹2,47,500" in reply["text"]
    assert rig.wire.of("audio_start") == [{"type": "audio_start", "sample_rate": 24_000}]
    assert rig.wire.audio and rig.wire.of("audio_end")
    assert set(rig.tts.languages) == {"hi"}
    assert len(rig.stt.heard) == 1 and len(rig.stt.heard[0]) >= 10 * FRAME_SAMPLES


async def test_events_arrive_in_the_order_the_client_needs(rig: Rig) -> None:
    await rig.speak()

    kinds = [event["type"] for event in rig.wire.events if event["type"] != "state"]
    assert kinds == ["transcript", "reply", "audio_start", "audio_end", "timing"]


async def test_playback_done_moves_on_to_waiting(rig: Rig) -> None:
    await rig.speak()
    assert rig.session.state == VoiceState.SPEAKING

    await rig.session.playback_done()

    assert rig.session.state == VoiceState.WAITING_FOR_NEXT_INPUT


async def test_a_client_that_never_reports_playback_is_timed_out(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cascade_pipeline, "PLAYBACK_GRACE_S", 0.05)

    await rig.speak()
    await asyncio.sleep(0.2)

    assert rig.session.state == VoiceState.WAITING_FOR_NEXT_INPUT


async def test_a_second_turn_works_after_the_first(rig: Rig) -> None:
    await rig.speak()
    await rig.session.playback_done()
    await rig.speak()

    assert len(rig.wire.of("reply")) == 2


async def test_audio_arriving_while_a_turn_is_worked_out_is_ignored(rig: Rig) -> None:
    rig.stt.gate = asyncio.Event()
    await rig.speak(wait=False)

    await rig.session.receive_audio(UTTERANCE * 2)
    rig.stt.gate.set()
    assert rig.session._turn is not None
    await rig.session._turn

    assert len(rig.stt.heard) == 1 and len(rig.wire.of("reply")) == 1


async def test_an_empty_transcript_goes_back_to_waiting_without_a_reply(rig: Rig) -> None:
    rig.stt.text = ""

    await rig.speak()

    assert rig.wire.of("reply") == [] and rig.wire.audio == []
    assert rig.session.state == VoiceState.WAITING_FOR_NEXT_INPUT


async def test_an_stt_failure_is_reported_and_the_session_carries_on(rig: Rig) -> None:
    rig.stt.fail = True
    await rig.speak()

    assert rig.wire.of("error") and rig.wire.states[-2:] == ["ERROR", "WAITING_FOR_NEXT_INPUT"]
    assert "type your question" in rig.wire.of("error")[0]["message"]

    rig.stt.fail = False
    await rig.speak()
    assert len(rig.wire.of("reply")) == 1


async def test_when_tts_fails_the_reply_is_still_delivered_as_text(rig: Rig) -> None:
    rig.tts.fail = True

    await rig.speak()

    assert rig.wire.of("reply") and rig.wire.of("audio_unavailable")
    assert rig.wire.audio == [] and rig.wire.of("audio_end") == []
    assert rig.session.state == VoiceState.WAITING_FOR_NEXT_INPUT


async def test_each_sentence_is_synthesised_and_sent_separately(client: AsyncClient) -> None:
    text = "Your visit is booked for Monday at 10 AM. Please bring a photo ID with you."
    rig = Rig(await make_user(), ScriptedLLM(script=[text], route="general"))
    rig.stt.text = "hello there"

    await rig.speak()

    assert rig.tts.spoken == [
        "Your visit is booked for Monday at 10 AM.",
        "Please bring a photo ID with you.",
    ]
    assert len(rig.wire.audio) == 2 and len(rig.wire.of("audio_start")) == 1


async def test_reply_chunking_sends_the_whole_reply_in_one_request(client: AsyncClient) -> None:
    text = "Your visit is booked for Monday at 10 AM. Please bring a photo ID with you."
    rig = Rig(await make_user(), ScriptedLLM(script=[text]), chunking="reply")
    rig.stt.text = "hello there"

    await rig.speak()

    assert rig.tts.spoken == [text]


# --- barge-in ---------------------------------------------------------------------------


async def test_speaking_over_the_reply_stops_it(rig: Rig) -> None:
    rig.tts.gate = asyncio.Event()  # the reply is still being synthesised
    await rig.speak(wait=False)
    await rig.tts.started.wait()
    assert rig.session.state == VoiceState.SPEAKING

    await rig.session.receive_audio(tone(12 * FRAME_MS))

    assert rig.wire.of("stop_audio") == [{"type": "stop_audio"}]
    assert rig.wire.audio == [] and rig.wire.of("audio_end") == []
    assert rig.session.state == VoiceState.LISTENING
    assert rig.wire.of("reply"), "the reply text was already delivered"


async def test_speaking_during_client_playback_also_stops_it(rig: Rig) -> None:
    await rig.speak()
    assert rig.wire.of("audio_end") and rig.session.state == VoiceState.SPEAKING

    await rig.session.receive_audio(tone(12 * FRAME_MS))

    assert rig.wire.of("stop_audio") and rig.session.state == VoiceState.LISTENING


async def test_the_interrupting_utterance_becomes_the_next_turn(rig: Rig) -> None:
    rig.tts.gate = asyncio.Event()
    await rig.speak(wait=False)
    await rig.tts.started.wait()
    rig.tts.gate = None

    await rig.session.receive_audio(UTTERANCE)
    assert rig.session._turn is not None
    await rig.session._turn

    assert len(rig.wire.of("reply")) == 2 and len(rig.stt.heard) == 2


async def test_a_short_noise_while_speaking_does_not_interrupt(rig: Rig) -> None:
    await rig.speak()

    # Long enough to start a normal utterance, too short to count as barge-in
    await rig.session.receive_audio(tone(4 * FRAME_MS) + silence(400))

    assert rig.wire.of("stop_audio") == [] and rig.session.state == VoiceState.SPEAKING


async def test_barge_in_is_recorded(rig: Rig) -> None:
    rig.tts.gate = asyncio.Event()
    await rig.speak(wait=False)
    await rig.tts.started.wait()

    await rig.session.receive_audio(tone(12 * FRAME_MS))

    analytics = await TurnAnalytics.find_all().to_list()
    assert [a.barged_in for a in analytics] == [True]
    assert analytics[0].spoken is False


# --- guardrails -------------------------------------------------------------------------


@pytest.mark.guardrail
async def test_the_estimate_disclaimer_is_spoken_not_only_shown(rig: Rig) -> None:
    await rig.speak()

    assert rig.wire.of("reply")[0]["disclaimer"] == ESTIMATE_DISCLAIMER["hi"]
    assert ESTIMATE_DISCLAIMER["hi"] in " ".join(rig.tts.spoken)


@pytest.mark.guardrail
async def test_a_spoken_otp_gets_the_warning_and_reaches_no_model(client: AsyncClient) -> None:
    llm = ScriptedLLM(script=["anything"])
    rig = Rig(await make_user(), llm)
    rig.stt.text = "my otp is 4 8 2 9 1 3"

    await rig.speak()

    assert "Muthoot will never ask for your OTP" in " ".join(rig.tts.spoken)
    assert rig.wire.of("reply")[0]["blocked"] is True
    assert llm.calls == []


@pytest.mark.guardrail
async def test_a_model_asking_for_an_otp_is_never_spoken(client: AsyncClient) -> None:
    rig = Rig(await make_user(), ScriptedLLM(script=["Please share your OTP to continue."]))
    rig.stt.text = "hello there"

    await rig.speak()

    spoken = " ".join(rig.tts.spoken)
    assert "share your OTP" not in spoken
    assert SAFE_FALLBACK["en"] in spoken
    assert rig.wire.of("reply")[0]["blocked"] is True


@pytest.mark.guardrail
async def test_analytics_keep_timings_and_labels_but_nothing_that_was_said(rig: Rig) -> None:
    await rig.speak()

    record = (await TurnAnalytics.find_all().to_list())[0]
    stored = str(record.model_dump())
    assert "30 gram" not in stored and "2,47,500" not in stored
    assert "user_id" not in record.model_dump()
    assert record.pipeline == "cascade" and record.intent == "calculator"
    assert record.stt_provider == "fake-stt" and record.tts_provider == "fake-tts"
    assert set(record.stages) == {
        "end_of_speech_ms", "stt_ms", "routing_ms", "llm_ms", "tts_first_chunk_ms", "ttfa_ms",
        "total_ms",
    }  # fmt: skip
    assert rig.wire.of("timing")[0]["stages"] == record.stages


async def test_time_to_first_audio_includes_the_silence_the_vad_waited_for(rig: Rig) -> None:
    await rig.speak()

    stages = rig.wire.of("timing")[0]["stages"]
    assert stages["ttfa_ms"] >= stages["end_of_speech_ms"] >= 0
    assert stages["total_ms"] >= stages["ttfa_ms"]


async def test_mock_tts_returns_silence_of_a_sensible_length() -> None:
    speech = await MockTTS().synthesize("Hello there")

    assert speech.sample_rate == 24_000 and 0.4 < speech.seconds < 0.7
    assert set(speech.pcm16) == {0}


# --- a shorter first piece --------------------------------------------------------------


def test_a_long_first_sentence_is_cut_at_a_comma() -> None:
    first = "For 30 grams of 22 carat gold, you could get about Rs 2,22,700 to Rs 2,47,500."

    head, tail = shorten_first([first, "Shall I book a visit?"])[:2]

    assert head == "For 30 grams of 22 carat gold,"
    assert tail == "you could get about Rs 2,22,700 to Rs 2,47,500."


def test_without_a_comma_it_is_cut_at_a_word() -> None:
    first = "30 ग्राम 22 कैरेट सोने पर आपको लगभग ₹2,22,700 से ₹2,47,500 तक का लोन मिल सकता है।"

    pieces = shorten_first([first])

    assert len(pieces) == 2 and " ".join(pieces) == first
    assert len(pieces[0]) <= 60 and not pieces[0].endswith(" ")


@pytest.mark.parametrize(
    "chunks",
    [[], ["A short reply that needs no cut."], ["x" * 100]],  # the last has nowhere to cut
)
def test_short_or_uncuttable_first_sentences_are_left_alone(chunks: list[str]) -> None:
    assert shorten_first(chunks) == chunks
