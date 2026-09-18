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
# NO OUTBOUND-EMAIL MUTING FIXTURE ANY MORE
# ---------------------------------------------------------------------------
#
# An autouse `mock_email` fixture used to live here, replacing
# auth.service._send_verification_email / _send_password_reset_email
# with no-ops so that registration and password-reset tests would not
# block trying to reach Mailgun or Postfix from inside the test
# container.
#
# It is gone because both targets are gone, and with them the hazard.
# This product does not send email: it writes a `notification_request`
# row into the outbox and the comms service delivers. Under test,
# settings.comms_api_url is empty, so the emitters return without even
# writing a row -- there is no socket to open and nothing to mute. A
# fixture patching two names that no longer exist would fail at
# collection; one patching something else would be protecting against a
# send this tree cannot perform.
#
# A test that needs the code or the token now reads it from where it
# actually is: the user row for the verification code, or the emitted
# outbox payload for the reset token (see test_auth_password_reset.py's
# capture_reset_email, which sets comms_api_url first so the row is
# written at all).


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

      password_reset:127.0.0.1
          -- password-reset request/confirm, shared key (same shape as
          email_auth above -- see auth/router.py header). Cleared for
          the same reason: a rate-limit test earlier in the run must
          not bleed a 429 into an unrelated password-reset test.

      totp_login_verify:127.0.0.1
          -- TASK-38 2FA POST /auth/2fa/login-verify, IP-keyed same
          shape as email_auth/password_reset above (and deliberately
          tighter: 5 per 300s, not 5 per 60s -- see auth/router.py's
          auth_2fa_login_verify docstring). The OTHER three 2FA rate
          limits (totp_setup/totp_confirm/totp_disable) are keyed by
          user.id, not IP -- every test registers its own fresh user,
          so those are naturally isolated per test and need no cleanup
          here.
    """
    try:
        from app.core.redis import get_redis

        redis = get_redis()
        await redis.delete("email_auth:127.0.0.1")
        await redis.delete("password_reset:127.0.0.1")
        await redis.delete("totp_login_verify:127.0.0.1")
        async for key in redis.scan_iter(match="auth_rate:*"):
            await redis.delete(key)
    except RuntimeError:
        # Redis singleton not yet initialised (test collection error path).
        pass
