"""Fetch the Silero VAD model (ONNX, about 1.2 MB) into ../models/, which git ignores.

The same file faster-whisper ships, so the VAD code is the one CareFlow was measured with.

    python -m scripts.get_vad_model
"""

from pathlib import Path

import httpx

from config import get_settings

URL = (
    "https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/"
    "faster_whisper/assets/silero_vad_v6.onnx"
)


def main() -> None:
    target = Path(get_settings().silero_vad_model)
    if target.is_file():
        print(f"Already there: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    response = httpx.get(URL, follow_redirects=True, timeout=60)
    response.raise_for_status()
    target.write_bytes(response.content)
    print(f"Saved {len(response.content):,} bytes to {target}")


if __name__ == "__main__":
    main()
