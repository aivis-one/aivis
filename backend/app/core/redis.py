# =============================================================================
# AIVIS.ONE Backend -- Redis Connection
# =============================================================================
#
# LIFECYCLE:
#   App startup  -> init_redis()  -> creates client + connection pool
#   App running  -> get_redis()   -> returns shared client
#   App shutdown -> close_redis() -> closes all connections cleanly
#
# Managed by FastAPI lifespan in main.py.
#
# USAGE:
#   from app.core.redis import get_redis
#   redis = get_redis()
#   await redis.set("key", "value", ex=300)
#   value = await redis.get("key")
# =============================================================================

import redis.asyncio as aioredis

from app.core.config import settings

# Global client -- initialized at startup, None before init_redis().
_redis_client: aioredis.Redis | None = None  # type: ignore[type-arg]


async def init_redis() -> None:
    """Initialize the Redis client. Called once at app startup."""
    global _redis_client
    _redis_client = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url,
        decode_responses=True,  # auto-decode bytes -> str
    )


async def close_redis() -> None:
    """Close the Redis client. Called once at app shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    """Get the shared Redis client instance.

    Raises:
        RuntimeError: If called before init_redis().
    """
    if _redis_client is None:
        raise RuntimeError(
            "Redis client not initialized. "
            "Ensure init_redis() is called at app startup."
        )
    return _redis_client
