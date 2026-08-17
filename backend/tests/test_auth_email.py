# =============================================================================
# AIVIS.ONE Backend -- Email Auth Tests (Sprint 1.1)
# =============================================================================
#
# Tests cover:
#   1-4:   Registration (success, duplicate, weak password, invalid email)
#   5-9:   Login (success, wrong password, non-existent, blocked, platform)
#   10-12: Logout, logout invalid token, logout-all
#   13:    Session limit eviction (MAX_CONCURRENT_SESSIONS)
#
# Email prefix: "s11_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.users.models import User
from tests.helpers import auth_headers, login_user, register_user



# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """Register with valid email + password -> 201, AuthResponse."""
    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": f"ok_{uuid.uuid4().hex[:12]}@example.com", "password": "strongpass1"},
    )
    assert resp.status_code == 201
    body = resp.json()

    assert "session_token" in body
    assert body["user"]["role"] == "investor"
    assert body["user"]["is_active"] is True
    assert body["user"]["onboarding_step"] == "registered"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """Register with an already-used email -> 409."""
    email = f"dup_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": email, "password": "strongpass1"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient) -> None:
    """Register with password < 8 chars -> 422."""
    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": f"weak_{uuid.uuid4().hex[:12]}@example.com", "password": "short"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient) -> None:
    """Register with malformed email -> 422."""
    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": "not-an-email", "password": "strongpass1"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """Login with correct credentials -> 200, AuthResponse."""
    email = f"login_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    data = await login_user(client, email=email)
    assert "session_token" in data
    assert data["user"]["role"] == "investor"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    """Login with wrong password -> 401."""
    email = f"wrongpw_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password_writes_audit_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A failed login must leave a `user.login_failed` row in audit_log.

    TASK-22: this is shipped behaviour that NO test covered. The 401 above
    proves the login was refused; it says nothing about whether the attempt
    was RECORDED -- and the recording is the entire security value, because
    an unrecorded failed login is invisible to any later investigation.

    The write is unusual and that is why it deserves its own test rather
    than an extra assertion on the 401: `_record_login_failure`
    (auth/service.py:222-251) opens its OWN session and commits it, because
    the caller's session is rolled back on the exception that produces the
    401. It also swallows its own errors by design -- "errors are logged but
    do not block auth flow" -- so if that write ever breaks, NOTHING fails
    and NOTHING 500s. The row simply stops appearing.

    Assertion is on event + target_id, not on the row count: other tests in
    this file also fail logins, and a count would couple this test to them.
    """
    from app.core.audit import AuditLog

    email = f"auditfail_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    # `User.email` is a plain Python PROPERTY reading credentials["email"]["email"]
    # (users/models.py:198) -- it is NOT a column. Used in a `where`, it evaluates
    # on the CLASS to None, the predicate becomes false, and the query returns
    # nothing with no error at all. The first draft of this test did exactly that
    # and failed on `.scalar_one()` as if the USER were missing.
    # The JSONB path below is the idiom the rest of this suite already uses
    # (helpers.py:238, and eleven lines further down in this same file).
    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()

    # CONTROL: no such row exists yet for this brand-new user. Without it a
    # row left by any earlier test could satisfy the assertion below.
    before = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.event == "user.login_failed",
                AuditLog.target_id == user.id,
            )
        )
    ).scalars().first()
    assert before is None, "fresh user must have no prior login_failed row"

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "definitely-not-the-password"},
    )
    assert resp.status_code == 401

    # The helper committed on its OWN session. Rolling back here ends the
    # read transaction the "before" query opened, so the next statement is
    # guaranteed to see that commit under any isolation level. The fixture
    # is a plain session on the shared engine -- it wraps nothing, so this
    # discards no test state.
    await db_session.rollback()
    after = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.event == "user.login_failed",
                AuditLog.target_id == user.id,
            )
        )
    ).scalars().first()
    assert after is not None, (
        "a failed login must write user.login_failed to audit_log -- "
        "_record_login_failure swallows its own errors, so a silent "
        "regression here produces no other symptom"
    )
    assert after.data.get("reason")


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient) -> None:
    """Login with email that doesn't exist -> 401."""
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": f"ghost_{uuid.uuid4().hex[:12]}@example.com", "password": "whatever1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_blocked_user(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Login with is_active=False -> 401."""
    email = f"blocked_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    # Deactivate the user directly in DB.
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "testpass123"},
    )
    assert resp.status_code == 401


# NOTE: test_login_platform_user was removed. It mutated a regular
# investor into role=PLATFORM and never reverted, leaving the DB with
# two Platform users -- causing MultipleResultsFound cascades in 111
# downstream tests. The scenario was also architecturally impossible:
# the real Platform user from seed_platform.py has credentials.email
# == null, so email-login cannot find it. No coverage was lost.


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient) -> None:
    """Logout with valid token -> 204, subsequent request -> 401."""
    email = f"logout_{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Logout.
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(token),
    )
    assert resp.status_code == 204

    # Token should be invalid now.
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(token),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalid_token(client: AsyncClient) -> None:
    """Logout with garbage token -> 401."""
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers("garbage-token-xyz"),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_all(client: AsyncClient) -> None:
    """Logout-all invalidates all sessions for the user."""
    email = f"logoutall_{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email=email)

    # Create a second session by logging in again.
    data2 = await login_user(client, email=email)
    token1 = data["session_token"]
    token2 = data2["session_token"]

    # Logout-all using token1.
    resp = await client.post(
        "/api/v1/auth/logout-all",
        headers=auth_headers(token1),
    )
    assert resp.status_code == 204

    # Both tokens should be invalid now.
    resp1 = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(token1),
    )
    resp2 = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(token2),
    )
    assert resp1.status_code == 401
    assert resp2.status_code == 401


# ---------------------------------------------------------------------------
# Session limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_limit_evicts_oldest(client: AsyncClient) -> None:
    """Creating more sessions than MAX_CONCURRENT_SESSIONS evicts oldest.

    Register creates session #1. Then login MAX times to fill up + overflow.
    The first token (from register) should be evicted.
    """
    # Session eviction (max_concurrent_sessions) and auth rate limit
    # (auth_rate_limit_max_requests) are independent invariants that
    # happen to share a numeric default of 5. Sending 1 register + 5
    # logins back-to-back from a single IP would hit the rate limit
    # before exercising the eviction logic. Reset the auth-rate-limit
    # Redis key before each request so we test eviction in isolation.
    from app.core.redis import get_redis
    redis = get_redis()
    rate_limit_key = "email_auth:127.0.0.1"

    email = f"limit_{uuid.uuid4().hex[:12]}@example.com"
    password = "testpass123"
    max_sessions = settings.max_concurrent_sessions  # default 5

    # Session #1 from register.
    await redis.delete(rate_limit_key)
    data = await register_user(client, email=email, password=password)
    first_token = data["session_token"]

    # Sessions #2 .. #(max + 1) from login.
    # After this loop, we have max+1 sessions created total,
    # so the oldest (first_token) should have been evicted.
    for _ in range(max_sessions):
        await redis.delete(rate_limit_key)
        await login_user(client, email=email, password=password)

    # First token should be evicted -- request with it fails.
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(first_token),
    )
    assert resp.status_code == 401
