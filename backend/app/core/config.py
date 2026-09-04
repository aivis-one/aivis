# =============================================================================
# AIVIS.ONE Backend -- Application Configuration
# =============================================================================
#
# APP_VERSION: single source of truth for API version.
#   Used in FastAPI app init and GET / response.
#
# All settings loaded from environment variables (or .env file).
# Pydantic-settings validates types and applies defaults automatically.
#
# APP_ENV (R51, fail-closed):
#   REQUIRED, no default. An unset or empty APP_ENV refuses to start
#   the application -- the pre-R51 default of "development" silently
#   enabled the entire dev profile (CORS *, dev webhook secrets, dev
#   DB fallback) on any host missing its .env. The empty-string
#   sentinel below exists only so the validator can raise a readable
#   error instead of pydantic's bare "Field required".
#   Anything other than "development" is treated as production-grade.
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
    # R51: empty sentinel, NOT a default -- the validator rejects it
    # first thing (see APP_ENV note in the module header).
    app_env: str = ""
    log_level: str = "INFO"
    cors_origins: str = "*"
    # Base URL of the deployed frontend SPA (no trailing slash). Used to
    # build absolute links the backend emails out -- currently only the
    # password-reset confirm link (auth/service.py::_send_password_reset_email
    # -> f"{frontend_base_url}/password-reset/confirm?token=..."). Not
    # gated behind the is_dev validator like secret_key/database_url:
    # an unset value in production degrades to a broken (but harmless,
    # non-secret-leaking) link in one email body, not an open security
    # hole -- so this stays a plain default rather than a hard failure.
    frontend_base_url: str = "http://localhost:5173"

    # -- Database --
    database_url: str = ""

    # -- Redis --
    redis_url: str = "redis://localhost:6379/0"

    # -- MinIO (S3-compatible object storage, Refactor 2 iter 2.1) --
    # Backend uses the service account credentials (ACCESS_KEY/SECRET_KEY),
    # NOT the root credentials. Root creds live in .env only because
    # docker-compose and minio-init need them at bootstrap. They are not
    # mapped here -- the BaseSettings extra="ignore" silently drops them.
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "aivis-attachments"
    minio_region: str = "us-east-1"
    # Presigned URL TTL: short for authenticated download, long for public.
    minio_presigned_ttl_auth: int = 900       # 15 minutes
    minio_presigned_ttl_public: int = 86400   # 24 hours
    # Hard limit on uploaded file size. Mirrored in nginx client_max_body_size.
    # Files larger than this are rejected at ingress; backend trusts the
    # ingress because Staff-driven upload happens exclusively via MinIO Web
    # UI (see Refactor 2 §3.7), not through the API.
    minio_max_file_size_mb: int = 100

    # -- Auth --
    secret_key: str = ""
    session_ttl_days: int = 30
    max_concurrent_sessions: int = 5
    # Avatar sessions (staff impersonating a user) do NOT inherit
    # session_ttl_days -- TASK-6 4.3, owner-ruled: a working shift, not a
    # month. Independent knob so changing it never touches ordinary logins.
    avatar_session_ttl_hours: int = 8
    # THE AVATAR RESTRICTION SWITCH -- owner-ruled 2026-08-17.
    # Default False: an admin in avatar mode may do EVERYTHING, because the
    # product is being tested single-handedly through the admin account and
    # a restriction that blocks the tester tests nothing. Set to True to put
    # every RESTRICTED_OPERATIONS guard back on at once.
    # This is step ONE of a two-step ruling: the second step replaces this
    # single flag with a per-operation toggle, and the division there is by
    # CAPABILITY, never by role (his words, 2026-08-17). The route wiring is
    # deliberately left in place so that step is an extension, not a rebuild.
    # The trigger he named for turning it back on is his own: real users and
    # real money.
    avatar_restrictions_enabled: bool = False

    # -- Telegram --
    telegram_bot_token: str = "TEST"

    # -- Telegram Auth Security --
    auth_rate_limit_max_requests: int = 5
    auth_rate_limit_window_seconds: int = 60
    auth_init_data_ttl_seconds: int = 300
    auth_clock_skew_seconds: int = 60

    # -- Email (SMTP primary, Mailgun fallback) --
    smtp_host: str = "host.docker.internal"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@mail.aivis.one"
    smtp_use_tls: bool = False
    mailgun_api_key: str = "TEST"
    mailgun_domain: str = "mail.aivis.one"
    # AIVIS.ONE runs in EU; production .env (generated by install_aivis.sh)
    # and .env.example both default to the EU endpoint. Override to
    # https://api.mailgun.net only for a US-region Mailgun account.
    mailgun_api_url: str = "https://api.eu.mailgun.net"
    high_secured_domains: str = ""

    # -- Crypto payments --
    #
    # THERE IS NO NETWORK LIST HERE ANY MORE, ON PURPOSE. CRYPTO_NETWORKS
    # held "TRC20,ERC20,BEP20,PoS" and had exactly one reader, the stub
    # address generator that this delivery removed. Renaming it to the
    # service's names would have left a setting that looks live and is
    # read by nobody -- worse than a stale one, because a stale setting
    # is visibly stale. Which networks are served is now the payments
    # service's fact and it answers 400 network_not_supported for the
    # rest (TOR section 11 p.12); a second list here would disagree with
    # that one silently, and the disagreement would only ever surface as
    # a user's refused deposit.
    #
    # FREEZING_HOURS_CRYPTO went with it for the same reason: its only
    # reader was the removed webhook. The cooling-off period for crypto
    # deposits is re-established by the receiver in H8, in whatever shape
    # that receiver needs.
    freezing_hours_bank: int = 72 * 14

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

    # -- Referral click rate limit (Task 1 Block B) --
    # Per-IP anti-abuse limit for POST /api/v1/public/referral-click.
    # This is NOT click deduplication: click_count is a raw counter by
    # design; the limit only caps how fast one IP can inflate it.
    referral_click_rate_limit_max_requests: int = 60
    referral_click_rate_limit_window_seconds: int = 60

    # -- Social proof cache --
    social_proof_cache_ttl: int = 300

    # -- Volume Bonuses (Sprint 7.3) --
    # Basis points: 200 = 2.00%, 100 = 1.00%.
    volume_bonus_monthly_bp: int = 200
    volume_bonus_quarterly_bp: int = 100
    leaderboard_top_monthly: int = 20
    leaderboard_top_quarterly: int = 10
    leaderboard_worker_interval_minutes: int = 60

    # -- Events (iter 2.7b) --
    # Ceiling for GET /api/v1/events/upcoming?limit=N. The dashboard
    # widget asks for 3; this bounds an over-large client request so the
    # query stays cheap. Clamped in posts/service.py::list_upcoming_events
    # (an oversized limit degrades to this value, not a 422).
    events_upcoming_max_limit: int = 50

    # -- Comms integration: outbox relay (T-63) --
    # The transactional-outbox relay (core/events/relay.py) ships rows of
    # outbox_events to the comms Redis Stream.
    #
    # NOTE: comms_redis_url is NOT redis_url above. redis_url is this
    # application's own cache/rate-limit instance; comms_redis_url points
    # at the COMMS stack's Redis, a different server on the shared docker
    # network. They are never the same value on a real box.
    #
    # COMMS_REDIS_URL is written into backend/.env by the installer
    # hand-over (scripts/install_aivis.sh, setup_comms); an EMPTY url
    # means "there is no relay" -- it disables the background task with a
    # log line instead of failing to start. Local dev has no comms stack.
    comms_redis_url: str = ""
    # Stream name the relay XADDs into. The default MIRRORS the comms
    # consumer's own default (comms app/core/config.py:66
    # `comms_events_stream: str = "comms:events"`, verified against that
    # code for this delivery): a name mismatch means events land in a
    # stream nobody reads, silently. Override ONLY in lockstep with the
    # comms .env.
    comms_events_stream: str = "comms:events"
    # Relay tick interval (seconds between passes over the outbox).
    comms_relay_interval_seconds: float = 2.0
    # Rows claimed per pass (the FOR UPDATE SKIP LOCKED batch).
    comms_relay_batch_size: int = 100
    # A poison row logs WARNING every N failed attempts and INFO in
    # between -- loud enough for the operator, quiet enough not to drown
    # the log. Never a drop limit: outbox rows are not discarded.
    comms_relay_warn_every_attempts: int = 10
    # Exponential backoff for poison rows: delay = min(base * 2**attempts,
    # cap), computed from the POST-increment attempts (first failure ->
    # base * 2). Infrastructure failures never assign a backoff.
    comms_relay_backoff_base_seconds: float = 2.0
    comms_relay_backoff_cap_seconds: float = 300.0
    # Dead-letter ceiling: at this many failed attempts the row gets
    # dead_lettered_at, ONE error log, and leaves the relay's select.
    # With base 2.0 / cap 300 the pure-backoff path to death is
    # 4+8+16+32+64+128+256 + 4x300 ~= 28-35 min plus pass ticks.
    comms_relay_max_attempts: int = 12
    # Socket timeouts for the relay's Redis connection -- a hung TCP
    # connection must not stall the loop forever. A timeout surfaces as
    # redis TimeoutError, which the relay classifies as INFRASTRUCTURE
    # (pass aborted, attempts untouched).
    comms_relay_socket_connect_timeout_seconds: float = 5.0
    comms_relay_socket_timeout_seconds: float = 5.0
    # Operator switch for the background relay. True by default: on a box
    # where the installer has filled COMMS_REDIS_URL the relay is meant to
    # run. It is NOT a test toggle -- tests never start the lifespan
    # (ASGITransport fires no startup event) and dev has an empty url, so
    # both are already covered by the url gate.
    comms_relay_enabled: bool = True

    # -- Comms integration: HTTP API (T-64) --
    # The synchronous door into comms: the product creates a recipient
    # before its first message to that user, because a message to an
    # unknown recipient resolves to nothing and is dropped terminally on
    # the comms side (SKIPPED, no delivery row, no retry).
    #
    # Both values are written into backend/.env by the installer
    # hand-over, exactly like COMMS_REDIS_URL above; until this delivery
    # nothing read them. An EMPTY url means "this box has no comms
    # stack": no client is built and no call is made.
    comms_api_url: str = ""
    comms_service_token: str = ""
    # Per-request timeout. Deliberately short: this call sits inside the
    # registration transaction, so its ceiling is how long a registering
    # user waits when comms is unreachable.
    comms_http_timeout_seconds: float = 5.0

    # -- Payments service (H7) --
    #
    # The product is a client of the crypto payments service: it creates
    # invoices, shows their address, forwards the TXID the user submits
    # and reads the status back. Same shape as the comms pair above and
    # for the same reason -- an empty URL means "this box has no payments
    # stack", and that is a supported configuration rather than a fault.
    #
    # UNTIL THE DEPLOY HAND-OVER OF TOR SECTION 9 EXISTS, EMPTY IS THE
    # ONLY CONFIGURATION. The three product-side variables of that
    # section (PAYMENTS_SERVICE_TOKEN, PAYMENTS_API_URL and the webhook
    # secret, which is H8's) are generated by the service on its first
    # install pass, and the service cannot do that yet. So the deposit
    # screen reports "temporarily unavailable" on every box until that
    # work lands. That is not a regression: what it replaces is a screen
    # that displayed AIVIS_TRC20_<hex> as a deposit address, which no
    # wallet would accept and no transfer could reach.
    payments_api_url: str = ""
    payments_service_token: str = ""
    # Shared secret of the INBOUND direction (H8): the service sends it in
    # the X-Payments-Secret header of every webhook it delivers, and the
    # receiver compares it whole via hmac.compare_digest. Not a signature
    # over the body -- TOR section 8 chose a shared secret deliberately
    # and the header name says so.
    #
    # The receiver is fail-closed on an empty value here: an empty
    # configured secret rejects every event rather than accepting an
    # empty header, because compare_digest("", "") is true. That check
    # lives in the receiver and NOT in this validator, because this
    # validator does not run on a dev box (see the `not is_dev` gate
    # below) and a dev box must not become an open receiver.
    payments_webhook_secret: str = ""
    # Per-request timeout. Longer than the comms one and not by feel:
    # POST /invoices/{id}/txid does a synchronous explorer lookup with
    # the service's own retry loop above it, which TOR section 7 bounds
    # at four attempts and roughly seven seconds. A five-second ceiling
    # here would time out that call on its normal slow path and leave the
    # user unable to tell a busy explorer from a broken deposit.
    payments_http_timeout_seconds: float = 15.0

    # -- Computed properties --

    @property
    def is_dev(self) -> bool:
        """True when running in development mode."""
        return self.app_env == "development"

    @property
    def high_secured_domain_list(self) -> list[str]:
        """Parsed list of high-secured email domains (Mailgun-only delivery)."""
        return [d.strip().lower() for d in self.high_secured_domains.split(",") if d.strip()]

    @property
    def minio_max_file_size_bytes(self) -> int:
        """Hard upload limit converted to bytes."""
        return self.minio_max_file_size_mb * 1024 * 1024

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        """Apply dev defaults and enforce production requirements."""
        # -- APP_ENV is REQUIRED (R51, fail-closed) -- checked FIRST so
        # a missing value produces this message and not a cascade of
        # production-requirement errors.
        env = self.app_env.strip().lower()
        if not env:
            raise ValueError(
                "APP_ENV is required and has no default (fail-closed). "
                "Set APP_ENV=development for a dev box or "
                "APP_ENV=production for a deployment. Anything other "
                "than 'development' is treated as production-grade."
            )
        self.app_env = env
        is_dev = env == "development"

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
                "Set explicit origins, e.g. https://app.aivis.one"
            )

        # -- database_url --
        if not self.database_url:
            if is_dev:
                self.database_url = (
                    "postgresql+asyncpg://aivis:aivis@localhost:5432/aivis"
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

        # -- telegram_bot_token --
        if self.telegram_bot_token in ("", "TEST"):
            if not is_dev:
                raise ValueError(
                    "TELEGRAM_BOT_TOKEN must be set to a real token "
                    "in production (not 'TEST')."
                )

        # -- MinIO credentials (Refactor 2 iter 2.1) --
        # Required at runtime in any environment because the storage
        # abstraction is in the hot path of attachments / templates /
        # roadmap covers. Dev-only fallbacks would silently mask a
        # broken docker-compose stack.
        if not self.minio_endpoint:
            if is_dev:
                self.minio_endpoint = "http://localhost:9000"
            else:
                raise ValueError("MINIO_ENDPOINT is required in production.")

        if not self.minio_access_key:
            if is_dev:
                self.minio_access_key = "minioadmin"
            else:
                raise ValueError("MINIO_ACCESS_KEY is required in production.")

        if not self.minio_secret_key:
            if is_dev:
                self.minio_secret_key = "minioadmin"
            else:
                raise ValueError("MINIO_SECRET_KEY is required in production.")

        # -- Comms API pairing (T-64) --
        # A url without a token sends "Authorization: Bearer " and comms
        # answers 401 to every call: recipients would silently stop being
        # created, and the first symptom would be users who never receive
        # a notification. A token without a url is the same
        # half-configuration seen from the other side.
        #
        # Gated on "comms is INTENDED on this box" -- i.e. at least one of
        # the two is set -- rather than on their absence: a box with no
        # comms at all is a supported configuration (see the empty-url
        # note above), and demanding these keys everywhere would stop
        # every comms-less deployment from starting, including in-place
        # upgrades whose .env has no COMMS_* yet. Dev stays optional so a
        # laptop needs no comms stack.
        # -- the payments TRIPLE: url / token / webhook secret (H7, H8) --
        #
        # Same gate and same reasoning as the comms pair below: demanded
        # only when payments is INTENDED on this box, because a box with
        # no payments stack must still start -- and, until the section 9
        # hand-over exists, every box is one.
        #
        # WHY ALL THREE OR NONE, RATHER THAN A REQUIRED SECRET. H8 added
        # the third member. Making it required on its own would stop the
        # product from booting the moment this code lands and before the
        # installer that mints the value has landed -- and the installer
        # is a different delivery that may arrive later. Gating all three
        # on "any one of them is set" removes the ordering dependency
        # completely: a box with none of them boots, a box with all three
        # boots, and only a half-installed box is refused.
        #
        # Each member names what its absence breaks, because "half
        # configured" alone does not tell an installer which half.
        if not is_dev and (
            self.payments_api_url
            or self.payments_service_token
            or self.payments_webhook_secret
        ):
            missing = [
                name
                for name, value in (
                    ("PAYMENTS_API_URL", self.payments_api_url),
                    ("PAYMENTS_SERVICE_TOKEN", self.payments_service_token),
                    ("PAYMENTS_WEBHOOK_SECRET", self.payments_webhook_secret),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Half-configured payments stack: "
                    f"{', '.join(missing)} empty while the rest is set. "
                    "PAYMENTS_API_URL missing -> the client has no address "
                    "to call. PAYMENTS_SERVICE_TOKEN missing -> the service "
                    "answers 401 to every call, which this client maps to "
                    '"unavailable", so the deposit screen reports a '
                    "transient outage forever. PAYMENTS_WEBHOOK_SECRET "
                    "missing -> the receiver is fail-closed and rejects "
                    "every event delivered to it, so confirmed payments "
                    "never reach a balance. Set all three, or clear all "
                    "three to run without payments."
                )

        if not is_dev and (self.comms_api_url or self.comms_service_token):
            if self.comms_api_url and not self.comms_service_token:
                raise ValueError(
                    "COMMS_API_URL is set but COMMS_SERVICE_TOKEN is "
                    "empty: comms would reject every call with 401 and "
                    "recipients would never be created. Set the token or "
                    "clear the URL."
                )
            if self.comms_service_token and not self.comms_api_url:
                raise ValueError(
                    "COMMS_SERVICE_TOKEN is set but COMMS_API_URL is "
                    "empty: half-configured comms client. Set the URL or "
                    "clear the token."
                )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
