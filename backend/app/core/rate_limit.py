# =============================================================================
# CBSHOME Backend -- Rate Limiting (Sprint 5.2 fix: SEC-5)
# =============================================================================
#
# Generic IP-based rate limiter using Redis INCR + EXPIRE pattern.
# Extracted from auth/telegram.py to be reusable across auth methods.
#
# PATTERN:
#   INCR on first request sets count=1, EXPIRE sets the window.
#   Subsequent requests within the window increment the counter.
#   TTL is set only on first increment to avoid resetting the window.
#
# USAGE:
#   from app.core.rate_limit import check_rate_limit
#   await check_rate_limit(f"email_auth:{ip_address}")
# =============================================================================

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.core.redis import get_redis


async def check_rate_limit(key: str) -> None:
    """Check rate limit for the given key.

    Uses Redis INCR + EXPIRE pattern. TTL is set only on the first
    increment to avoid resetting the window on subsequent requests.

    Args:
        key: Redis key for rate limiting (e.g. "email_auth:1.2.3.4").

    Raises:
        BadRequestError: If rate limit is exceeded.
    """
    redis = get_redis()

    count = await redis.incr(key)
    if count == 1:
        # Set TTL only on first increment -- don't reset the window.
        await redis.expire(key, settings.auth_rate_limit_window_seconds)

    if count > settings.auth_rate_limit_max_requests:
        raise BadRequestError(
            "Too many auth attempts. Please try again later."
        )
