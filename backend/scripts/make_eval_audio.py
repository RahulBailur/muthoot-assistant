"""Synthesise a few labelled utterances as speech, for the voice latency benchmark.

Spoken by Gnani in a different voice from the assistant's own, so the benchmark never hears
the assistant talking to itself. Output is 16 kHz mono WAV under eval/audio/, which is
gitignored and can be rebuilt at any time. Existing files are kept, so credits are spent
only once: about 0.1 credit per sentence.

    python -m scripts.make_eval_audio                      # the benchmark set below
    python -m scripts.make_eval_audio --ids en-01,hi-01
"""

import argparse
import asyncio
import json
import os
import wave
from pathlib import Path

# The usage counter needs a database; an in-memory one is enough here
os.environ["ENVIRONMENT"] = "test"
os.environ["USE_MOCK_DB"] = "true"
os.environ.setdefault("JWT_SECRET", "eval-audio-secret-not-used-for-anything")

EVAL_DIR = Path(__file__).parent.parent / "eval"
AUDIO_DIR = EVAL_DIR / "audio"
SPEAKER_VOICE = "Prakash"  # a timbre-v3.0 voice that is not the assistant's
# One question per agent and language worth timing: the headline demo first
BENCH_IDS = ["hi-01", "en-01", "en-07", "en-10", "ml-01", "ta-01"]


def load_utterances(name: str = "utterances.jsonl") -> list[dict[str, str]]:
    lines = (EVAL_DIR / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def audio_path(utterance_id: str) -> Path:
    return AUDIO_DIR / f"{utterance_id}.wav"


def write_wav(path: Path, pcm16: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm16)


def read_wav(path: Path) -> bytes:
    """PCM16 mono 16 kHz, as written by this script."""
    with wave.open(str(path), "rb") as wav:
        return wav.readframes(wav.getnframes())


async def main() -> int:
    from config import get_settings
    from database import init_db
    from services.tts import GnaniTTS, TTSUnavailable
    from voice.audio_utils import SAMPLE_RATE, float_to_pcm16, pcm16_to_float, resample

    parser = argparse.ArgumentParser(description="Synthesise benchmark utterances as speech")
    parser.add_argument("--ids", default=",".join(BENCH_IDS))
    args = parser.parse_args()

    settings = get_settings()
    await init_db()
    speaker = GnaniTTS(
        settings.gnani_api_key,
        settings.gnani_tts_model,
        SPEAKER_VOICE,
        SAMPLE_RATE,
        settings.gnani_timeout_s,
    )
    wanted = {row["id"]: row for row in load_utterances()}
    made = skipped = failed = 0
    for utterance_id in args.ids.split(","):
        row, path = wanted[utterance_id], audio_path(utterance_id)
        if path.exists():
            skipped += 1
            continue
        try:
            speech = await speaker.synthesize(row["text"], row["lang"])
        except TTSUnavailable as error:
            failed += 1
            print(f"  {utterance_id}: could not synthesise ({error})")
            continue
        audio = resample(pcm16_to_float(speech.pcm16), speech.sample_rate, SAMPLE_RATE)
        write_wav(path, float_to_pcm16(audio), SAMPLE_RATE)
        made += 1
    print(f"{made} made, {skipped} already there, {failed} failed -> {AUDIO_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
