# =============================================================================
# CBSHOME Backend -- Application Configuration
# =============================================================================
#
# All settings are loaded from environment variables (or .env file).
# Pydantic-settings validates types and applies defaults automatically.
#
# ENVIRONMENTS:
#   development -- safe defaults, relaxed validation
#   production  -- strict validation, required secrets
#
# USAGE:
#   from app.core.config import settings
#   settings.database_url
# =============================================================================

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # -- KYC (SumSub) --
    sumsub_api_key: str = "TEST"
    sumsub_secret_key: str = "TEST"

    # -- Email (EMAP primary, Mailgun fallback) --
    emap_api_key: str = "TEST"
    mailgun_api_key: str = "TEST"
    mailgun_domain: str = ""

    # -- Crypto payments --
    # Comma-separated list of supported networks.
    crypto_networks: str = "TRC20,ERC20,BEP20,PoS"
    freezing_hours_crypto: int = 1
    freezing_hours_bank: int = 72 * 14   # 14-day cooling-off for fiat

    # -- Installments --
    installment_default_days: int = 7
    installment_worker_hour: int = 3     # UTC hour to run daily daemon

    # -- Agent --
    agent_application_cooldown_days: int = 30

    # -- Social proof cache --
    social_proof_cache_ttl: int = 300    # seconds

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
                raise ValueError(
                    "DATABASE_URL is required in production."
                )

        if not self.secret_key:
            if is_dev:
                self.secret_key = (
                    "dev-only-insecure-key-do-not-use-in-production"
                )
            else:
                raise ValueError(
                    "SECRET_KEY is required in production. "
                    'Generate: python -c "import secrets; print(secrets.token_urlsafe(64))"'
                )

        _valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in _valid_levels:
            raise ValueError(
                f"log_level must be one of {_valid_levels}, got '{self.log_level}'"
            )
        if not is_dev and self.log_level.upper() == "DEBUG":
            raise ValueError("log_level DEBUG is not allowed in production.")

        if not is_dev and self.cors_origins == "*":
            raise ValueError(
                "CORS_ORIGINS must not be '*' in production."
            )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def is_dev(self) -> bool:
        """True when running in development mode."""
        return self.app_env == "development"

    @property
    def crypto_network_list(self) -> list[str]:
        """Parsed list of supported crypto networks."""
        return [n.strip() for n in self.crypto_networks.split(",")]


# Singleton: one Settings instance for the entire application.
settings = Settings()
