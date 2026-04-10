# =============================================================================
# CBSHOME Backend -- Rate Limiting (Sprint 5.2 fix: SEC-5, fix Sprint 6.1)
# =============================================================================
#
# Generic IP-based rate limiter using Redis.
#
# Sprint 6.1 FIX:
#   Replaced non-atomic INCR + EXPIRE with Lua script.
#   Original pattern: if process crashes between INCR and EXPIRE,
#   the key lives forever (no TTL). Lua script executes atomically.
#
# USAGE:
#   from app.core.rate_limit import check_rate_limit
#   await check_rate_limit(f"email_auth:{ip_address}")
# =============================================================================

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.core.redis import get_redis

# Lua script: INCR + conditional EXPIRE in one atomic operation.
# Sets TTL only when counter transitions from 0 to 1 (new window).
# Returns the current count after increment.
_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


async def check_rate_limit(key: str) -> None:
    """Check rate limit for the given key.

    Uses Lua script for atomic INCR + EXPIRE. TTL is set only on the
    first increment to avoid resetting the window on subsequent requests.

    Args:
        key: Redis key for rate limiting (e.g. "email_auth:1.2.3.4").

    Raises:
        BadRequestError: If rate limit is exceeded.
    """
    redis = get_redis()

    count = await redis.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        settings.auth_rate_limit_window_seconds,
    )

    if count > settings.auth_rate_limit_max_requests:
        raise BadRequestError(
            "Too many auth attempts. Please try again later."
        )
