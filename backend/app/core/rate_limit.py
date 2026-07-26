# =============================================================================
# AIVIS.ONE Backend -- Rate Limiting (Sprint 5.2 fix: SEC-5, fix Sprint 6.1,
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
# iter 2.5-finishing FIX:
#   On exceeded limit, raise RateLimitError (HTTP 429) with
#   retry_after_seconds populated from the Redis key TTL. The global
#   AivisError handler in main.py turns retry_after_seconds into the
#   standard `Retry-After` response header. Previously the helper raised
#   BadRequestError (HTTP 400), which was semantically wrong and forced
#   clients to parse the error message to distinguish rate-limit hits
#   from genuine bad requests.
#
#   The Lua script now returns {count, ttl} instead of just count.
#   For the boundary case (first request in a fresh window) it returns
#   the configured window as ttl directly -- no separate TTL round-trip.
#   For subsequent requests it asks Redis for the live TTL so Retry-After
#   shrinks naturally as the window ages.
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
from app.core.exceptions import RateLimitError
from app.core.redis import get_redis

# Lua script: INCR + conditional EXPIRE in one atomic operation.
# Sets TTL only when counter transitions from 0 to 1 (new window).
# Returns {count, ttl} -- on the first increment ttl == ARGV[1]
# (the configured window); on subsequent increments ttl is the live
# remaining TTL from Redis so Retry-After shrinks as the window ages.
_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
local ttl
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
else
    ttl = redis.call('TTL', KEYS[1])
end
return {count, ttl}
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
        RateLimitError: If rate limit is exceeded. Carries
            retry_after_seconds for the global handler to surface as
            the HTTP Retry-After response header.
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

    result = await redis.eval(
        _RATE_LIMIT_SCRIPT,
        1,
        key,
        window,
    )

    # Lua returns a 2-element table -- redis-py surfaces it as a list.
    count, ttl = int(result[0]), int(result[1])

    if count > limit:
        # ttl can be -1 (no expiry) or -2 (key gone) in pathological
        # cases. Translate either to None so the Retry-After header is
        # simply omitted rather than emitting a misleading negative value.
        retry_after = ttl if ttl > 0 else None
        raise RateLimitError(
            message=error_message,
            retry_after_seconds=retry_after,
        )
