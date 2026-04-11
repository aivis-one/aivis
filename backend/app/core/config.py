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

# Valid structlog log levels.
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


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

    # -- Crypto Webhook (Sprint 5.2) --
    # Shared secret for blockchain webhook authentication (stub).
    # In production, replace with provider-specific signature validation.
    crypto_webhook_secret: str = ""

    # -- Payment confirmation daemon (Sprint 5.3) --
    confirmation_worker_interval_minutes: int = 5

    # -- Installments --
    installment_default_days: int = 7
    installment_worker_hour: int = 3

    # -- Withdrawals (Sprint 6.3) --
    min_withdrawal_cents: int = 1000       # $10.00
    max_withdrawal_cents: int = 10000000   # $100,000.00

    # -- Agent --
    agent_application_cooldown_days: int = 30

    # -- Social proof cache --
    social_proof_cache_ttl: int = 300

    # -- Notifications (Sprint 8.1) --
    notification_max_delivery_attempts: int = 3
    notification_worker_interval_minutes: int = 1

    # -- Volume Bonuses (Sprint 7.3) --
    # Basis points: 200 = 2.00%, 100 = 1.00%.
    volume_bonus_monthly_bp: int = 200
    volume_bonus_quarterly_bp: int = 100
    leaderboard_top_monthly: int = 20
    leaderboard_top_quarterly: int = 10
    leaderboard_worker_interval_minutes: int = 60

    # -- Computed properties --

    @property
    def is_dev(self) -> bool:
        """True when running in development mode."""
        return self.app_env == "development"

    @property
    def crypto_network_list(self) -> list[str]:
        """Parsed list of crypto networks from comma-separated string."""
        return [n.strip() for n in self.crypto_networks.split(",") if n.strip()]

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        """Apply dev defaults and enforce production requirements."""
        is_dev = self.app_env == "development"

        # -- log_level --
        if self.log_level.upper() not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid LOG_LEVEL: {self.log_level}. "
                f"Valid: {', '.join(sorted(_VALID_LOG_LEVELS))}"
            )
        self.log_level = self.log_level.upper()

        # -- CORS in production --
        if not is_dev and self.cors_origins.strip() == "*":
            raise ValueError(
                "CORS_ORIGINS=* is not allowed in production. "
                "Set explicit origins, e.g. https://cbshome.org"
            )

        # -- database_url --
        if not self.database_url:
            if is_dev:
                self.database_url = (
                    "postgresql+asyncpg://cbshome:cbshome@localhost:5432/cbshome"
                )
            else:
                raise ValueError("DATABASE_URL is required in production.")

        # -- secret_key --
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

        # -- kyc_webhook_secret --
        if not self.kyc_webhook_secret:
            if is_dev:
                self.kyc_webhook_secret = "dev-webhook-secret"
            else:
                raise ValueError(
                    "KYC_WEBHOOK_SECRET is required in production."
                )

            # -- crypto_webhook_secret (Sprint 5.2) --
            if not self.crypto_webhook_secret:
                if is_dev:
                    self.crypto_webhook_secret = "dev-crypto-webhook-secret"
                else:
                    raise ValueError(
                        "CRYPTO_WEBHOOK_SECRET is required in production."
                    )

            # -- telegram_bot_token --
            if self.telegram_bot_token in ("", "TEST"):
                if not is_dev:
                    raise ValueError(
                        "TELEGRAM_BOT_TOKEN must be set to a real token "
                        "in production (not 'TEST')."
                    )

            return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
