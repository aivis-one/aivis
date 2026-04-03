# =============================================================================
# CBSHOME Backend -- Application Configuration
# =============================================================================
#
# APP_VERSION: single source of truth for API version.
#   Used in FastAPI app init and GET / response.
#
# All settings loaded from environment variables (or .env file).
# Pydantic-settings validates types and applies defaults automatically.
# =============================================================================

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source of truth for API version.
# Import as: from app.core.config import APP_VERSION, settings
APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # -- Application --
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "*"

    # -- Database --
    database_url: str = ""

    # -- Redis --
    redis_url: str = "redis://localhost:6379/0"

    # -- Auth --
    secret_key: str = ""
    session_ttl_days: int = 30
    max_concurrent_sessions: int = 5

    # -- Telegram --
    telegram_bot_token: str = "TEST"

    # -- Telegram Auth Security --
    auth_rate_limit_max_requests: int = 5
    auth_rate_limit_window_seconds: int = 60
    auth_init_data_ttl_seconds: int = 300
    auth_clock_skew_seconds: int = 60

    # -- KYC (SumSub) --
    sumsub_api_key: str = "TEST"
    sumsub_secret_key: str = "TEST"

    # -- KYC Webhook --
    # Shared secret for webhook authentication (stub).
    # In production, replace with SumSub signature validation.
    kyc_webhook_secret: str = ""

    # -- Email (EMAP primary, Mailgun fallback) --
    emap_api_key: str = "TEST"
    mailgun_api_key: str = "TEST"
    mailgun_domain: str = ""

    # -- Crypto payments --
    crypto_networks: str = "TRC20,ERC20,BEP20,PoS"
    freezing_hours_crypto: int = 1
    freezing_hours_bank: int = 72 * 14

    # -- Installments --
    installment_default_days: int = 7
    installment_worker_hour: int = 3

    # -- Agent --
    agent_application_cooldown_days: int = 30

    # -- Social proof cache --
    social_proof_cache_ttl: int = 300

    # -- Notifications --
    notification_max_delivery_attempts: int = 3

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        """Apply dev defaults and enforce production requirements."""
        is_dev = self.app_env == "development"

        if not self.database_url:
            if is_dev:
                self.database_url = (
                    "postgresql+asyncpg://cbshome:cbshome@localhost:5432/cbshome"
                )
            else:
                raise ValueError("DATABASE_URL is required in production.")

        if not self.secret_key:
            if is_dev:
                self.secret_key = (
                    "dev-only-insecure-key-do-not-use-in-production"
                )
            else:
                raise ValueError(
                    "SECRET_KEY is required in production. "
                    "Generate with: python -c "
                    "\"import secrets; print(secrets.token_urlsafe(64))\""
                )

        if not self.kyc_webhook_secret:
            if is_dev:
                self.kyc_webhook_secret = "dev-webhook-secret"
            else:
                raise ValueError(
                    "KYC_WEBHOOK_SECRET is required in production."
                )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
