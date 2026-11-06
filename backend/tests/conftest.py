import os
from collections.abc import AsyncIterator

# Must be set before any application module reads its settings
os.environ["ENVIRONMENT"] = "test"
os.environ["USE_MOCK_DB"] = "true"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-bytes-long"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["RATE_LIMIT_AUTH"] = "1000/minute"  # the rate-limit test sets its own
os.environ["SEED_DEFAULT_PASSWORD"] = "seed-password-1"
os.environ["REDIS_URL"] = ""  # tests that want a cache build one on fakeredis
# Never a real model in tests, whatever the developer's own .env says
os.environ["LLM_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = ""
os.environ["OLLAMA_MODEL"] = ""
os.environ["INTENT_EMBEDDING_MODEL"] = ""
os.environ["RATE_LIMIT_CHAT"] = "1000/minute"
# Never a paid speech API in tests either
os.environ["STT_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"
os.environ["GNANI_API_KEY"] = ""
os.environ["VOICE_MAX_TTS_CHARS"] = "0"
os.environ["VOICE_MAX_STT_SECONDS"] = "0"
os.environ["VAD_PROVIDER"] = "energy"
os.environ["VAD_SILENCE_MS"] = "200"
os.environ["RATE_LIMIT_VOICE_SESSIONS"] = "3/minute"
# Fixed values, whatever the developer's own .env says
os.environ["GOLD_RATE_24K_PER_GRAM"] = "12000"
os.environ["LTV_LIMIT"] = "0.75"
os.environ["ESTIMATE_DEDUCTION"] = "0.10"
os.environ["AUCTION_GRACE_DAYS"] = "30"
os.environ["OTP_TTL_S"] = "300"
os.environ["OTP_MAX_ATTEMPTS"] = "3"
os.environ["OTP_REVEAL_IN_RESPONSE"] = "true"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from database import close_db, init_db  # noqa: E402
from main import app  # noqa: E402
from rate_limit import limiter  # noqa: E402


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client against the app, with a fresh in-memory database per test."""
    await init_db()
    limiter.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    close_db()
