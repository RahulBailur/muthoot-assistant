"""Measure the voice pipeline turn by turn, against a running server.

Each utterance is streamed over /ws/voice at the speed it would be spoken, exactly as the
browser does. The server reports its own per-stage timings for every turn; this script
collects them and prints P50 / P95 per stage.

    python -m scripts.make_eval_audio                      # once: synthesise the questions
    python -m eval.latency_bench --label baseline
    python -m eval.latency_bench --label "after X" --rounds 2 --save

Every turn spends real Gnani credits (STT and TTS, about 0.4 credit a turn).
With few turns a P95 is close to the slowest turn: the turn count is printed with it.
`--save` writes eval/results/<label>.json (timings and labels only, nothing that was said).
"""

import argparse
import asyncio
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
import httpx

from config import get_settings
from scripts.make_eval_audio import BENCH_IDS, audio_path, read_wav
from services.analytics import percentile

RESULTS_DIR = Path(__file__).parent / "results"
CHUNK_MS = 100
CHUNK_BYTES = 16_000 * 2 * CHUNK_MS // 1000
TURN_TIMEOUT_S = 120.0

# Printed in this order; the names are the server's (voice/timing.py)
STAGES = [
    ("end_of_speech_ms", "End-of-speech detection"),
    ("stt_ms", "Speech to text (Gnani)"),
    ("routing_ms", "Routing"),
    ("llm_ms", "Assistant (model and tools)"),
    ("tts_first_chunk_ms", "First sentence spoken (Gnani)"),
    ("ttfa_ms", "Time to first audio"),
    ("total_ms", "Whole turn"),
]


def summarise(turns: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """{stage: {n, p50, p95, min, max}} over the turns that reached that stage."""
    summary = {}
    for stage, _ in STAGES:
        values = [turn["stages"][stage] for turn in turns if stage in turn["stages"]]
        if values:
            summary[stage] = {
                "n": len(values),
                "p50": percentile(values, 50),
                "p95": percentile(values, 95),
                "min": min(values),
                "max": max(values),
            }
    return summary


def count_by(turns: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for turn in turns:
        label = str(turn.get(key) or "none")
        counts[label] = counts.get(label, 0) + 1
    return counts


def report(label: str, turns: list[dict[str, Any]]) -> str:
    lines = [
        f"{label}: {len(turns)} turns",
        f"{'stage':32} {'n':>3} {'P50':>9} {'P95':>9} {'max':>9}",
    ]
    for stage, name in STAGES:
        stats = summarise(turns).get(stage)
        if stats:
            p50, p95, worst = (stats[key] / 1000 for key in ("p50", "p95", "max"))
            lines.append(f"{name:32} {stats['n']:>3} {p50:>7.2f} s {p95:>7.2f} s {worst:>7.2f} s")
    lines.append(f"intents: {count_by(turns, 'intent')}")
    lines.append(f"routed by: {count_by(turns, 'routed_by')}")
    lines.append(f"answered by: {count_by(turns, 'answered_by')}")
    lines.append(f"spoken by: {count_by(turns, 'tts_provider')}")
    return "\n".join(lines)


async def run_turn(ws: aiohttp.ClientWebSocketResponse, pcm: bytes) -> dict[str, Any] | None:
    """Speak one utterance and wait for the server's timing report."""
    for start in range(0, len(pcm), CHUNK_BYTES):
        await ws.send_bytes(pcm[start : start + CHUNK_BYTES])
        await asyncio.sleep(CHUNK_MS / 1000)
    spoken_until = time.monotonic()

    quiet, stop = b"\x00\x00" * (CHUNK_BYTES // 2), asyncio.Event()

    async def keep_silent() -> None:  # a real microphone never stops sending
        while not stop.is_set():
            await ws.send_bytes(quiet)
            await asyncio.sleep(CHUNK_MS / 1000)

    silence = asyncio.create_task(keep_silent())
    turn: dict[str, Any] = {"intent": None, "heard": False}
    transcribing = False
    try:
        async with asyncio.timeout(TURN_TIMEOUT_S):
            while True:
                message = await ws.receive()
                if message.type == aiohttp.WSMsgType.BINARY:
                    turn.setdefault(
                        "client_ttfa_ms", round((time.monotonic() - spoken_until) * 1000, 1)
                    )
                elif message.type == aiohttp.WSMsgType.TEXT:
                    event = json.loads(message.data)
                    if event["type"] == "transcript":
                        turn["heard"] = True
                    elif event["type"] == "reply":
                        turn["intent"] = event["intent"]
                    elif event["type"] == "timing":
                        turn.update({k: v for k, v in event.items() if k != "type"})
                        return turn
                    elif event["type"] == "state" and event["state"] == "TRANSCRIBING":
                        transcribing = True
                    elif event["type"] == "state" and event["state"] == "WAITING_FOR_NEXT_INPUT":
                        # After transcribing with nothing heard, the server just waits again
                        if transcribing and not turn["heard"]:
                            return None
                else:
                    raise ConnectionError(f"connection closed ({ws.close_code})")
    finally:
        stop.set()
        await silence
        await ws.send_json({"type": "playback_done"})


async def login(url: str, phone: str) -> str:
    """Log a seeded customer in with the demo OTP, as the login page does."""
    async with httpx.AsyncClient(base_url=url) as client:
        sent = await client.post("/api/auth/otp/request", json={"phone": phone})
        sent.raise_for_status()
        code = sent.json().get("demo_otp")
        if not code:
            raise SystemExit("The server does not reveal the demo OTP (OTP_REVEAL_IN_RESPONSE).")
        verified = await client.post("/api/auth/otp/verify", json={"phone": phone, "otp": code})
        verified.raise_for_status()
        return str(verified.json()["access_token"])


async def main() -> int:
    parser = argparse.ArgumentParser(description="Voice pipeline latency benchmark")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--phone", default="9000000201", help="a seeded customer")
    parser.add_argument("--label", default="run")
    parser.add_argument("--rounds", type=int, default=1, help="times through the question set")
    parser.add_argument("--gap", type=float, default=3.0, help="seconds between turns")
    parser.add_argument("--hardware", default="", help="a note stored with the results")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ids = [i for i in BENCH_IDS if audio_path(i).exists()] * args.rounds
    if not ids:
        print("No audio found. Run: python -m scripts.make_eval_audio")
        return 1

    token = await login(args.url, args.phone)
    turns: list[dict[str, Any]] = []
    async with (
        aiohttp.ClientSession() as http,
        http.ws_connect(f"{args.url.replace('http', 'ws', 1)}/ws/voice", max_msg_size=0) as ws,
    ):
        await ws.send_json({"type": "auth", "token": token})
        for index, utterance_id in enumerate(ids, 1):
            turn = await run_turn(ws, read_wav(audio_path(utterance_id)))
            if turn is None:
                print(f"  {index:>2}/{len(ids)} {utterance_id}: not heard")
                continue
            turn.pop("heard")
            turn["utterance"] = utterance_id
            turns.append(turn)
            ttfa = turn["stages"].get("ttfa_ms")
            shown = f"{ttfa / 1000:.1f} s to first audio" if ttfa else "not spoken"
            print(f"  {index:>2}/{len(ids)} {utterance_id}: {shown}")
            await asyncio.sleep(args.gap)
        await ws.send_json({"type": "end"})

    if not turns:
        print("No turn completed.")
        return 1
    print()
    print(report(args.label, turns))
    if args.save:
        settings = get_settings()
        RESULTS_DIR.mkdir(exist_ok=True)
        path = RESULTS_DIR / f"{args.label.replace(' ', '-').lower()}.json"
        result = {
            "label": args.label,
            "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "config": {
                "stt": f"{settings.stt_provider}:{settings.gnani_stt_model}",
                "tts": f"{settings.tts_provider}:{settings.gnani_tts_model}",
                "vad": settings.vad_provider,
                "vad_silence_ms": settings.vad_silence_ms,
                "llm_provider": settings.llm_provider,
                "llm_model": settings.gemini_text_model,
                "tts_chunking": settings.tts_chunking,
            },
            "hardware": args.hardware or platform.processor(),
            "summary": summarise(turns),
            "turns": turns,
        }
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
