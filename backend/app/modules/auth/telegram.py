# =============================================================================
# CBSHOME Backend -- Telegram Auth (Sprint 1.2, fix review)
# =============================================================================
#
# RESPONSIBILITIES:
#   1. Validate Telegram WebApp initData (HMAC-SHA256)
#   2. Anti-replay protection (Redis SET NX)
#   3. Rate limiting per telegram_id (delegates to core rate_limit)
#
# TELEGRAM initData VALIDATION:
#   Telegram sends a query string signed with HMAC-SHA256.
#   We verify the signature using our bot token to ensure the data
#   is authentic and not forged. See:
#   https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
#
# ANTI-REPLAY (WARNING-4):
#   Each initData hash is stored in Redis with TTL=auth_init_data_ttl_seconds.
#   A second request with the same initData within the window is rejected.
#   Key: init_data_used:{sha256(init_data)}
#
# RATE LIMITING (CRITICAL-4):
#   Max auth_rate_limit_max_requests per auth_rate_limit_window_seconds
#   per telegram_id. Delegates to atomic Lua-based check_rate_limit()
#   from core/rate_limit.py.
#   Key: auth_rate:{telegram_id}
# =============================================================================

import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote

import structlog
from app.core.config import settings
from app.core.rate_limit import check_rate_limit
from app.core.redis import get_redis

logger = structlog.get_logger()


class TelegramValidationError(Exception):
    """Raised when initData signature, content, or security check fails."""


# ---------------------------------------------------------------------------
# initData HMAC-SHA256 validation
# ---------------------------------------------------------------------------


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """Validate and parse Telegram WebApp initData.

    Args:
        init_data: Raw query string from Telegram WebApp.
        bot_token: Bot token from BotFather.

    Returns:
        Parsed user data dict from Telegram.

    Raises:
        TelegramValidationError: If signature is invalid or data expired.
    """
    # Parse the query string into key-value pairs.
    parsed = parse_qs(init_data, keep_blank_values=True)

    # Extract hash -- Telegram includes it for verification.
    received_hash = parsed.pop("hash", [None])[0]
    if not received_hash:
        raise TelegramValidationError("Missing hash in initData")

    # Build the data-check-string: sorted key=value pairs joined by \n.
    data_check_pairs = sorted(f"{k}={v[0]}" for k, v in parsed.items())
    data_check_string = "\n".join(data_check_pairs)

    # Compute HMAC-SHA256:
    # 1. secret_key = HMAC-SHA256("WebAppData", bot_token)
    # 2. hash = HMAC-SHA256(secret_key, data_check_string)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256,
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks.
    if not hmac.compare_digest(computed_hash, received_hash):
        raise TelegramValidationError("Invalid initData signature")

    # Check auth_date is present and not too old.
    auth_date_str = parsed.get("auth_date", [None])[0]
    if not auth_date_str:
        raise TelegramValidationError("Missing auth_date")

    try:
        auth_date = int(auth_date_str)
    except ValueError:
        raise TelegramValidationError("Invalid auth_date format") from None

    now = int(datetime.now(UTC).timestamp())

    if now - auth_date > settings.auth_init_data_ttl_seconds:
        raise TelegramValidationError("initData expired")

    # Reject auth_date from the future (clock skew tolerance from config).
    # Without this, an attacker can set auth_date far in the future,
    # making the token valid indefinitely (now - future_date < 0 < ttl).
    if auth_date > now + settings.auth_clock_skew_seconds:
        raise TelegramValidationError("initData auth_date is in the future")

    # Parse user JSON from the query string.
    user_data_str = parsed.get("user", [None])[0]
    if not user_data_str:
        raise TelegramValidationError("Missing user in initData")

    # Guard against malformed JSON in user field.
    try:
        user_data = json.loads(unquote(user_data_str))
    except json.JSONDecodeError:
        raise TelegramValidationError(
            "Invalid user data in initData"
        ) from None

    return user_data


# ---------------------------------------------------------------------------
# Anti-replay protection
# ---------------------------------------------------------------------------


async def check_init_data_replay(init_data: str) -> None:
    """Reject replayed initData within the validity window.

    Each initData hash is stored in Redis with TTL=auth_init_data_ttl_seconds.
    A second request with the same initData is rejected immediately.

    Args:
        init_data: Raw Telegram initData string (already HMAC-validated).

    Raises:
        TelegramValidationError: If this initData was already used.
    """
    redis = get_redis()
    init_data_hash = hashlib.sha256(init_data.encode()).hexdigest()
    replay_key = f"init_data_used:{init_data_hash}"

    # SET NX: only succeeds if key doesn't exist yet.
    # Returns True if set (first use), None if already existed.
    was_set = await redis.set(
        replay_key, "1", ex=settings.auth_init_data_ttl_seconds, nx=True,
    )
    if not was_set:
        raise TelegramValidationError("initData already used")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


async def check_auth_rate_limit(telegram_id: int) -> None:
    """Rate limit auth attempts per telegram_id.

    Delegates to the atomic Lua-based check_rate_limit() from core.
    Rate-limit hits raise RateLimitError (HTTP 429) which the global
    handler in main.py surfaces directly with Retry-After. Earlier
    revisions wrapped that into TelegramValidationError -> 400, which
    erased the distinction between "bad request" (invalid hash, replay)
    and "too many requests" -- restored in iter 2.5-finishing.

    Args:
        telegram_id: Telegram user ID (from validated initData).

    Raises:
        RateLimitError: If rate limit is exceeded. Propagates to the
            global AivisError handler; not wrapped here.
    """
    await check_rate_limit(f"auth_rate:{telegram_id}")
