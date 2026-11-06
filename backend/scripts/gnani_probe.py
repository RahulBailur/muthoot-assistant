"""Measure what one Gnani call costs, by spending as few credits as possible.

Gnani's docs do not say what a credit counts, so we find out: note the dashboard's
"credits left", run one step, and note it again.

    python -m scripts.gnani_probe tts         # 1 TTS call: one short sentence
    python -m scripts.gnani_probe roundtrip   # 1 TTS call + 1 STT call of that audio

STT cost = (credits used by roundtrip) - (credits used by tts).
Uses GNANI_API_KEY from .env. Prints sizes, timings and the transcript; never the key.
"""

import asyncio
import os
import sys
import time

# An in-memory database for the usage counter: nothing here touches real data
os.environ["ENVIRONMENT"] = "test"
os.environ["USE_MOCK_DB"] = "true"
os.environ.setdefault("JWT_SECRET", "probe-secret-not-used-for-anything")

SENTENCE = "नमस्ते, मैं आपकी गोल्ड लोन सहायक हूँ।"  # "Hello, I am your gold loan assistant."


async def main(mode: str) -> None:
    import numpy as np

    from config import get_settings
    from database import init_db
    from services.stt import GnaniSTT
    from services.tts import GnaniTTS
    from voice.audio_utils import SAMPLE_RATE, pcm16_to_float, resample

    settings = get_settings()
    if not settings.gnani_api_key:
        sys.exit("Set GNANI_API_KEY in .env first.")
    await init_db()

    tts = GnaniTTS(
        settings.gnani_api_key,
        settings.gnani_tts_model,
        settings.gnani_tts_voice,
        settings.gnani_tts_sample_rate,
        settings.gnani_timeout_s,
    )
    started = time.monotonic()
    speech = await tts.synthesize(SENTENCE, "hi")
    print(
        f"TTS: {len(SENTENCE)} characters -> {speech.seconds:.2f} s of audio at "
        f"{speech.sample_rate} Hz, in {time.monotonic() - started:.2f} s"
    )
    if mode != "roundtrip":
        return

    audio = resample(pcm16_to_float(speech.pcm16), speech.sample_rate, SAMPLE_RATE)
    stt = GnaniSTT(
        settings.gnani_api_key,
        settings.gnani_stt_model,
        settings.gnani_stt_language,
        settings.gnani_timeout_s,
    )
    started = time.monotonic()
    transcript = await stt.transcribe(audio.astype(np.float32))
    print(
        f"STT: {len(audio) / SAMPLE_RATE:.2f} s of audio -> [{transcript.language}] "
        f"{transcript.text!r}, in {time.monotonic() - started:.2f} s"
    )


if __name__ == "__main__":
    chosen = sys.argv[1] if len(sys.argv) > 1 else ""
    if chosen not in ("tts", "roundtrip"):
        sys.exit(__doc__)
    asyncio.run(main(chosen))
