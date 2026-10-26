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
#   THE SAME FOR REDIS (H42): the CLI points the run at a DEDICATED Redis
#   database of the same server (`-e REDIS_URL=.../<n>`) and tells the run
#   which number that is (`-e AIVIS_TEST_REDIS_DB=<n>`; the one literal is
#   TEST_REDIS_DB in scripts/aivis-manage.sh). The guard refuses a run
#   whose REDIS_URL names another database, or none: until H42 the suite
#   wrote into the live application's database 0 -- thousands of session
#   keys per run, and the rate-limit clean-up below deleting live people's
#   keys, a pending Telegram link among them.
#
# ISOLATION SCOPE:
#   Per-RUN: each run starts from a freshly created aivis_test and a
#   flushed test Redis database, so cross-run residue (the class of flakes
#   behind TD-068, and the Redis keyspace that grew with every run) cannot
#   accumulate.
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
#   * cheap_password_hashing   -- session-wide: argon2 at its minimum cost.
#   * production_password_hasher -- the hasher the code was imported with.
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

    The test suite shares one test DB and one test Redis database within
    a run, without transactional isolation. Parallel workers would race on
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

    import os

    refusal = non_test_redis_refusal(
        settings.redis_url, os.environ.get(TEST_REDIS_DB_ENV)
    )
    if refusal is not None:
        raise pytest.UsageError(refusal)


# The variable the CLI passes with the test Redis database's number. The
# number itself is written once, in scripts/aivis-manage.sh (TEST_REDIS_DB),
# and once more in .github/workflows/ci.yml, which says why.
TEST_REDIS_DB_ENV = "AIVIS_TEST_REDIS_DB"


def non_test_redis_refusal(redis_url: str, test_db: str | None) -> str | None:
    """Why the run may not use this Redis, or None when it may.

    The contract mirrors the database one: the run names its test Redis
    database (`AIVIS_TEST_REDIS_DB`), and REDIS_URL must point at exactly
    that one. Refused: no number given; a number that is not a whole
    number; 0, the application's own database; a REDIS_URL with no
    database in it (which a client reads as 0) or with any other one.
    Read with the redis client's own parser -- the number the suite's
    connections will use. Nothing is connected to, nothing secret is
    printed: only the two numbers.
    """
    from redis.connection import parse_url

    how = (
        "Run via `aivis test` or `aivis update`, which point the run at the "
        "test Redis database. To run pytest directly, export REDIS_URL "
        f"ending in /<n> and {TEST_REDIS_DB_ENV}=<n>, the same <n>, not 0."
    )
    if not test_db:
        return f"Refusing to run: {TEST_REDIS_DB_ENV} is not set. {how}"
    if not test_db.isdigit():
        return (
            f"Refusing to run: {TEST_REDIS_DB_ENV}={test_db!r} is not a number. "
            f"{how}"
        )
    if int(test_db) == 0:
        return (
            f"Refusing to run: {TEST_REDIS_DB_ENV}=0 is the application's own "
            f"Redis database. {how}"
        )
    try:
        url_db = parse_url(redis_url).get("db")
    except ValueError:
        url_db = None
    if url_db is None or int(url_db) != int(test_db):
        shown = "none" if url_db is None else str(url_db)
        return (
            f"Refusing to run: REDIS_URL names Redis database {shown}, not the "
            f"test database {test_db}. {how}"
        )
    return None


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

    WHAT IT SCANS, since H42: the run's own test Redis database (the
    guard in pytest_sessionstart), flushed at the start of every run, so
    the two SCANs walk a few hundred keys at most. Before H42 they walked
    the live application's whole keyspace before every test -- growing
    with every run -- and deleted live people's keys of these families.

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
        # The Telegram link flow: IP limits, per-e-mail code counts and
        # wrong-try locks, distinct-e-mail sets and the link tokens
        # themselves (every key starts `telegram_link`). A lock or a cap
        # reached by one test must not reach the next.
        async for key in redis.scan_iter(match="telegram_link*"):
            await redis.delete(key)
    except RuntimeError:
        # Redis singleton not yet initialised (test collection error path).
        pass


# ---------------------------------------------------------------------------
# Password hashing at its minimum cost (H42)
# ---------------------------------------------------------------------------
#
# Every registration hashes a password, every login verifies one, 2FA
# hashes its backup codes: with argon2's defaults (t=3, m=64 MiB, p=4)
# that is ~370 ms a hash on a 2-core box -- most of the suite's setup.
# The run swaps the module's hasher for argon2 at its minimum cost for the
# whole session and puts the original back at the end.
#
# The swap lives HERE and nowhere in the product: a setting that weakens
# password hashing is a lever that one day reaches production (owner
# ruling). Hashes made before the swap still verify -- an argon2 hash
# carries its own parameters -- and production_password_hasher hands the
# original to the one test that pins it to argon2's defaults.

_CHEAP_ARGON2 = {"time_cost": 1, "memory_cost": 8, "parallelism": 1}


@pytest.fixture(scope="session", autouse=True)
def cheap_password_hashing() -> Any:
    """The hasher the code was imported with, set aside for the run."""
    from argon2 import PasswordHasher

    from app.modules.auth import service as auth_service

    original = auth_service._ph
    auth_service._ph = PasswordHasher(**_CHEAP_ARGON2)
    try:
        yield original
    finally:
        auth_service._ph = original


@pytest.fixture
def production_password_hasher(cheap_password_hashing: Any) -> Any:
    """The product's own password hasher -- not the run's cheap one."""
    return cheap_password_hashing
