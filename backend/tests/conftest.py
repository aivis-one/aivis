# =============================================================================
# CBSHOME Backend -- pytest conftest (post-rollback, plain-DB edition)
# =============================================================================
#
# Tests run against the same Postgres database the dev site uses. There
# is no isolation infrastructure: no per-worker template DB clones, no
# bucket provisioning, no Redis-db swapping. Earlier attempts at that
# kind of isolation never actually worked -- the FastAPI app's engine
# initialised on import time, before any env-var override conftest
# could perform, so HTTP-driven tests always wrote to the live DB
# regardless of what conftest pretended.
#
# WHY THIS IS FINE:
#   * The dev DB is treated as disposable. install_cbshome.sh drops
#     and recreates it on every full reinstall.
#   * Tests achieve cross-run isolation by generating UUID-suffixed
#     emails (see tests/helpers.py register_user signature). No two
#     test runs collide on email-unique constraints.
#   * Tests that intentionally re-use one email (e.g. duplicate-email
#     check) opt in by passing email= explicitly.
#
# WHAT THIS LEAVES BEHIND:
#   * client                  -- AsyncClient backed by ASGITransport.
#   * db_session              -- AsyncSession from the app's session
#                                factory (writes to the live DB).
#   * mock_email autouse      -- swap _send_verification_email for a
#                                no-op so verification doesn't hit SMTP.
#   * clear_rate_limit autouse -- delete the email-auth Redis key so a
#                                 single test calling register_user
#                                 many times doesn't trip the limit.
# =============================================================================

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_session_factory
from app.main import app


# ---------------------------------------------------------------------------
# HTTP client + DB session
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Session-scoped boot: ASGITransport does not fire FastAPI's lifespan
# event, so init_redis / init_minio never run via the HTTP path. We do
# it once per pytest session here.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
async def init_app_resources() -> AsyncGenerator[None, None]:
    """Initialise the singletons that the HTTP layer expects to find.

    Without this, the first endpoint that calls get_redis() raises
    "Redis client not initialized". init_redis is idempotent enough
    that re-running across test sessions is safe.
    """
    from app.core.redis import close_redis, init_redis

    await init_redis()
    try:
        from app.core.minio import init_minio  # type: ignore[attr-defined]

        try:
            await init_minio()
        except Exception:
            # MinIO init may be sync, may not exist, may already be
            # initialised. We don't block tests on storage health.
            pass
    except ImportError:
        pass

    yield

    try:
        await close_redis()
    except Exception:
        pass


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient that drives the FastAPI app via ASGITransport.

    No background lifespan tasks are started -- ASGITransport does not
    fire startup/shutdown events. Tests that need daemon-side state
    (scheduler ticks, etc.) drive it directly via service calls, not
    via real lifespan.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[Any, None]:
    """AsyncSession against the live application DB.

    The session is opened from the same engine the HTTP layer uses, so
    a row a test commits here is visible to the next HTTP call this
    test makes (and vice versa).
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Autouse: mute outbound side effects
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the verification-email sender with a no-op.

    Without this, registration tests would block trying to reach
    Mailgun / Postfix from inside the test container.
    """

    async def _noop(_email: str, _code: str) -> None:
        return None

    monkeypatch.setattr(
        "app.modules.auth.service._send_verification_email", _noop
    )


@pytest.fixture(autouse=True)
async def clear_rate_limit() -> None:
    """Drop rate-limit Redis keys before each test.

    Covers both rate-limit families the auth flows use:

      email_auth:127.0.0.1
          -- email register / login keyed by client IP. Tests always
          come from 127.0.0.1 (ASGITransport), so a single fixed key.

      auth_rate:{telegram_id}
          -- Telegram auth keyed by telegram_id (int). Tests use a
          handful of fixed tg_ids in 100001..100099 and short TTLs
          would normally let them expire between runs, but a fast
          repeat of `cbshome update` can fire before TTL clears.
          Pattern-delete handles every tg_id the test suite has ever
          used without coupling conftest to the test-side constants.

    A single test that exceeds settings.auth_rate_limit_max_requests
    would otherwise hit a 429 and fail for no real reason.
    """
    try:
        from app.core.redis import get_redis

        redis = get_redis()
        await redis.delete("email_auth:127.0.0.1")
        async for key in redis.scan_iter(match="auth_rate:*"):
            await redis.delete(key)
    except RuntimeError:
        # Redis singleton not yet initialised (test collection error path).
        pass
