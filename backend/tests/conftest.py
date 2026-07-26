# =============================================================================
# AIVIS.ONE Backend -- pytest conftest (TD-068: dedicated test DB edition)
# =============================================================================
#
# Tests run against a DEDICATED `aivis_test` database, never the live dev
# DB. The `aivis test` / `aivis update` CLI provisions it per run --
# DROP + CREATE aivis_test, `alembic upgrade head`, minimal seed (platform
# user + platform templates) -- then invokes pytest with `-e DATABASE_URL`
# pointing at it. The lazy engine (app.core.database) reads
# settings.database_url on first use, so both the HTTP layer and db_session
# pick up that override automatically -- no monkeypatching here.
#
# FAIL-CLOSED INVARIANT (pytest_sessionstart):
#   A bare `pytest` that skipped the CLI provisioning would fall back to the
#   default DATABASE_URL -- the live dev DB -- and write to it. The
#   sessionstart guard aborts unless the target database name ends with
#   `_test`, so tests can never silently write to the live DB regardless of
#   entry point (IDE, CI, manual `docker compose exec app pytest`).
#
# ISOLATION SCOPE:
#   Per-RUN: each run starts from a freshly created aivis_test, so
#   cross-run residue (the class of flakes behind TD-068) cannot accumulate.
#   Per-TEST isolation is NOT provided -- tests still share state within a
#   single run (no rollback-per-test). That is a possible Stage-3b (savepoint
#   per test), gated on auditing for tests that fire concurrent requests on
#   one connection.
#
#   UUID-suffixed emails (tests/helpers.register_user) are retained -- now
#   belt-and-suspenders rather than the sole isolation mechanism.
#
# FIXTURES:
#   * client                  -- AsyncClient backed by ASGITransport.
#   * db_session              -- AsyncSession from the app's session factory
#                                (same engine as the HTTP layer).
#   * mock_email autouse      -- swap _send_verification_email for a no-op.
#   * clear_rate_limit autouse -- delete the email-auth Redis keys.
# =============================================================================

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from app.core.database import get_session_factory
from app.main import app
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Parallel-execution guard
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Refuse to run under pytest-xdist.

    The test suite shares a single dev DB and a single Redis instance
    without transactional isolation. Parallel workers would race on
    rate-limit keys, _platform/templates rows, UUID-suffixed-but-still-
    shared identifiers, and every other globally-mutable singleton the
    HTTP layer touches. Fail loud with a clear message instead of
    producing flaky results.

    Safe both when xdist is installed (option recognised, value
    truthy -> raise) and when it is not (option absent -> getoption
    returns None, no-op).
    """
    if config.getoption("numprocesses", None):
        raise pytest.UsageError(
            "pytest-xdist (-n / --numprocesses) is not supported: tests "
            "share a single test DB without transactional isolation. "
            "Run tests sequentially."
        )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Fail-closed guard: refuse to run unless the target DB is a test DB.

    TD-068 hybrid: the `aivis test` / `aivis update` CLI provisions a
    dedicated `aivis_test` database and points the app at it via
    `-e DATABASE_URL=...` before invoking pytest. This guard is the
    invariant backstop -- a bare `pytest` that skipped that provisioning
    would fall back to the default DATABASE_URL (the live dev DB) and write
    to it. Rather than let that happen silently, abort before the first
    query. The contract is purely the database NAME: it must end `_test`.

    Reads settings.database_url (which reflects the -e override) and parses
    just the name -- no engine, no connection, no secrets logged.
    """
    from sqlalchemy.engine.url import make_url

    from app.core.config import settings

    db_name = make_url(settings.database_url).database or ""
    if not db_name.endswith("_test"):
        raise pytest.UsageError(
            f"Refusing to run the test suite against database {db_name!r}: "
            "it is not a test database (name must end with '_test'). Run via "
            "`aivis test` or `aivis update`, which provision and target "
            "'aivis_test'. To run pytest directly, first export DATABASE_URL "
            "pointing at a *_test database."
        )


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
    from contextlib import suppress

    from app.core.redis import close_redis, init_redis

    await init_redis()
    try:
        from app.core.minio import init_minio  # type: ignore[attr-defined]

        # MinIO init may be sync, may not exist, may already be
        # initialised. We don't block tests on storage health.
        with suppress(Exception):
            await init_minio()
    except ImportError:
        pass

    yield

    with suppress(Exception):
        await close_redis()


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
          repeat of `aivis update` can fire before TTL clears.
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
