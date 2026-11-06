from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_JWT_SECRET = "change-me-to-a-long-random-string"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    environment: Literal["development", "test", "demo"] = "development"
    jwt_secret: str
    jwt_expiry_hours: int = 12
    mongo_uri: str = "mongodb://localhost:27017/goldloan"
    use_mock_db: bool = False
    # Empty switches the response cache off; a Redis that is down only costs a warning
    redis_url: str = ""
    response_cache_ttl_s: int = 3600
    bcrypt_rounds: int = 12
    rate_limit_auth: str = "10/minute"
    rate_limit_chat: str = "20/minute"
    llm_provider: Literal["gemini", "ollama", "mock"] = "mock"
    gemini_api_key: str = ""
    gemini_text_model: str = ""
    # A request slower than this counts as failed, and the next tier answers
    llm_timeout_s: float = 8.0
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""  # empty = no local tier
    ollama_timeout_s: float = 30.0
    # After this many failures in a row a provider is skipped for the cool-down
    gemini_breaker_threshold: int = 3
    gemini_breaker_cooldown_s: float = 60.0
    # Empty switches the embedding stage of the intent classifier off
    intent_embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Voice. The safe defaults call no paid API; real runs set gnani in .env
    stt_provider: Literal["gnani", "mock"] = "mock"
    tts_provider: Literal["gnani", "mock"] = "mock"
    gnani_api_key: str = ""
    gnani_stt_model: str = "prisma-v3.0"
    # indic-auto lets the model tell which of our languages was spoken
    gnani_stt_language: str = "indic-auto"
    gnani_tts_model: str = "timbre-v3.0"
    gnani_tts_voice: str = "Lakshmi"  # a timbre-v3.0 voice speaks all our languages
    gnani_tts_sample_rate: int = 24_000
    gnani_timeout_s: float = 15.0
    # Hard caps on Gnani use, counted in the database; 0 = no cap. Past a cap, voice turns
    # carry on as text, so the free credits are never run dry in the middle of a demo.
    voice_max_tts_chars: int = Field(default=0, ge=0)
    voice_max_stt_seconds: int = Field(default=0, ge=0)
    tts_cache_entries: int = Field(default=256, ge=0)  # synthesised sentences kept in memory
    vad_provider: Literal["silero", "energy"] = "energy"
    silero_vad_model: str = "../models/silero_vad_v6.onnx"
    vad_silence_ms: int = 500
    tts_chunking: Literal["sentence", "reply"] = "sentence"
    rate_limit_voice_sessions: str = "5/minute"
    # Mock OTP. There is no SMS gateway in the demo, so the code is returned in the response.
    otp_ttl_s: int = Field(default=300, gt=0)
    otp_max_attempts: int = Field(default=5, gt=0)
    otp_reveal_in_response: bool = True
    # Gold loan values. Mock figures: the real ones come from the client.
    gold_rate_24k_per_gram: int = Field(default=12500, gt=0)  # rupees, used when none is set
    ltv_limit: float = Field(default=0.75, gt=0, le=0.85)
    # Stones, wastage and the purity found at valuation can lower the value: the estimate's
    # low end is this much below the high end
    estimate_deduction: float = Field(default=0.10, ge=0, lt=1)
    # Days after maturity before an unpaid loan gets an auction notice
    auction_grace_days: int = Field(default=30, ge=0)
    seed_default_password: str = ""
    # Seed the mock dataset at start-up if the database has none: for hosts with no shell
    seed_on_start: bool = False
    frontend_build_dir: str = "../frontend/build"

    @model_validator(mode="after")
    def _check_runtime(self) -> Self:
        if self.use_mock_db and self.environment != "test":
            raise ValueError("USE_MOCK_DB=true is only allowed when ENVIRONMENT=test")
        if self.environment == "demo" and self.jwt_secret == PLACEHOLDER_JWT_SECRET:
            raise ValueError("JWT_SECRET must be changed from the placeholder for the demo")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
