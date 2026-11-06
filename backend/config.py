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
    # Empty switches the response cache off (used from M2)
    redis_url: str = ""
    bcrypt_rounds: int = 12
    rate_limit_auth: str = "10/minute"
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
