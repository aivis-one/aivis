# =============================================================================
# CBSHOME Backend -- Rate Limiting (Sprint 5.2 fix: SEC-5, fix Sprint 6.1,
#                                    extended Refactor 2 iter 2.2)
# =============================================================================
#
# Generic IP-based rate limiter using Redis.
#
# Sprint 6.1 FIX:
#   Replaced non-atomic INCR + EXPIRE with Lua script.
#   Original pattern: if process crashes between INCR and EXPIRE,
#   the key lives forever (no TTL). Lua script executes atomically.
#
# Refactor 2 iter 2.2 EXTENSION:
#   check_rate_limit() takes optional max_requests / window_seconds /
#   error_message kwargs so non-auth callers can apply their own limits
#   without forking the helper. Defaults (None) preserve the original
#   auth-flow behaviour: settings.auth_rate_limit_max_requests /
#   settings.auth_rate_limit_window_seconds and the original error
#   message ("Too many auth attempts ..."). Public-flow callers
#   (companies/attachments_public_router) pass explicit presets from
#   companies/constants.py PUBLIC_LIST_RATE_LIMIT and
#   PUBLIC_DOWNLOAD_RATE_LIMIT.
#
# USAGE:
#   # Auth-flow (unchanged):
#   from app.core.rate_limit import check_rate_limit
#   await check_rate_limit(f"email_auth:{ip_address}")
#
#   # Public-flow with explicit preset:
#   await check_rate_limit(
#       f"public_attach_list:{ip}",
#       max_requests=60,
#       window_seconds=60,
#       error_message="Too many requests. Please try again later.",
#   )
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


async def check_rate_limit(
    key: str,
    *,
    max_requests: int | None = None,
    window_seconds: int | None = None,
    error_message: str = "Too many auth attempts. Please try again later.",
) -> None:
    """Check rate limit for the given key.

    Uses Lua script for atomic INCR + EXPIRE. TTL is set only on the
    first increment to avoid resetting the window on subsequent requests.

    Args:
        key: Redis key for rate limiting (e.g. "email_auth:1.2.3.4").
        max_requests: Optional override for the request cap. Defaults to
            settings.auth_rate_limit_max_requests when None.
        window_seconds: Optional override for the rolling-window length.
            Defaults to settings.auth_rate_limit_window_seconds when None.
        error_message: Message surfaced to the client when the cap is
            exceeded. The default keeps the original auth-flow wording so
            existing tests and callers are unaffected.

    Raises:
        BadRequestError: If rate limit is exceeded.
    """
    redis = get_redis()

    window = (
        window_seconds
        if window_seconds is not None
        else settings.auth_rate_limit_window_seconds
    )
    limit = (
        max_requests
        if max_requests is not None
        else settings.auth_rate_limit_max_requests
    )

    count = await redis.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        window,
    )

    if count > limit:
        raise BadRequestError(error_message)
