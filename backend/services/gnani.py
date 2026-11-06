"""The client's speech provider, Gnani (Vachana APIs): what STT and TTS share.

- One API key, sent as the `X-API-Key-ID` header. It is never logged, and error messages
  never include a response body (it can echo the request).
- The key allows one active request at a time, so every call waits its turn here. A 429
  (another call still running) is retried once after a short pause.
- A 402 means the credits are used up. Then no call is made at all for a while, so a demo
  degrades to text at once instead of failing on every sentence.
"""

import asyncio
import time
import weakref
from typing import Any

import httpx

BASE_URL = "https://api.vachana.ai"
NO_CREDIT_PAUSE_S = 60 * 60
RETRY_AFTER_S = 0.5

# Language codes as Gnani names them
LANGUAGE_CODES = {"en": "en-IN", "hi": "hi-IN", "kn": "kn-IN", "ml": "ml-IN", "ta": "ta-IN"}

_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)
_no_credit_until = 0.0


class GnaniUnavailable(Exception):
    """The call was not made, or did not succeed."""


def _lock() -> asyncio.Lock:
    """One lock per event loop: the key allows a single request in flight."""
    loop = asyncio.get_running_loop()
    if loop not in _locks:
        _locks[loop] = asyncio.Lock()
    return _locks[loop]


def out_of_credit() -> bool:
    return time.monotonic() < _no_credit_until


def reset_credit_flag() -> None:
    global _no_credit_until
    _no_credit_until = 0.0


async def post(
    path: str,
    api_key: str,
    *,
    timeout_s: float,
    transport: httpx.AsyncBaseTransport | None = None,
    **request: Any,
) -> httpx.Response:
    """POST to Gnani, one call at a time. Returns only a 200 response."""
    global _no_credit_until
    if not api_key:
        raise GnaniUnavailable("GNANI_API_KEY is not set")
    if out_of_credit():
        raise GnaniUnavailable("Gnani credits are used up")
    async with _lock():
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(transport=transport, timeout=timeout_s) as client:
                    response = await client.post(
                        f"{BASE_URL}{path}", headers={"X-API-Key-ID": api_key}, **request
                    )
            except httpx.HTTPError as error:
                raise GnaniUnavailable(f"Gnani request failed: {type(error).__name__}") from error
            if response.status_code == httpx.codes.TOO_MANY_REQUESTS and attempt == 0:
                await asyncio.sleep(RETRY_AFTER_S)
                continue
            break
    if response.status_code == httpx.codes.PAYMENT_REQUIRED:
        _no_credit_until = time.monotonic() + NO_CREDIT_PAUSE_S
        raise GnaniUnavailable("Gnani credits are used up (HTTP 402)")
    if response.status_code != httpx.codes.OK:
        raise GnaniUnavailable(f"Gnani returned HTTP {response.status_code}")
    return response
