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
#
# TASK-38: 14-16 cover GET /sessions + DELETE /sessions/{id} (list,
# is_current marking, revoke-kills-target-only, revoke 404 on a
# nonexistent/foreign id). Row selection is by fresh-per-test data
# (each test registers its own unique user(s)), never by absolute
# count against shared state -- LESSONS.md.
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

    THE WRITE IS FIRE-AND-FORGET, AND THAT IS THE WHOLE REASON THIS TEST
    EXISTS. `_audit_login_failure` (auth/service.py:220) is dispatched via
    `background_tasks.add_task(...)` at service.py:411 -- it runs AFTER the
    response is returned, on its OWN session, with its own commit, and it
    catches and logs every exception rather than raising. So if that write
    ever breaks: the login still 401s, nothing fails, nothing 500s, and the
    row simply stops appearing. There is no other symptom to notice.

    Because it is a background task, the assertion has to WAIT for it. The
    poll below is not a sleep-until-green: it is the correct way to observe
    a write the framework deliberately performs after the response, and it
    is bounded so a genuine regression still fails rather than hangs.

    Assertion is on event + target_id, not on the row count: other tests in
    this file also fail logins, and a count would couple this test to them.
    """
    import asyncio
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

    # Capture the id as a PLAIN VALUE now, before anything can expire the
    # instance. `rollback()` below expires every ORM object in the session;
    # touching `user.id` afterwards would trigger a lazy refresh, and a lazy
    # refresh is IO -- in async SQLAlchemy that raises MissingGreenlet from
    # inside a plain attribute access, which reads like a driver fault rather
    # than what it is. This test hit exactly that on its second attempt.
    user_id = user.id

    # CONTROL: no such row exists yet for this brand-new user. Without it a
    # row left by any earlier test could satisfy the assertion below.
    before = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.event == "user.login_failed",
                AuditLog.target_id == user_id,
            )
        )
    ).scalars().first()
    assert before is None, "fresh user must have no prior login_failed row"

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "definitely-not-the-password"},
    )
    assert resp.status_code == 401

    # The background task runs after the response and commits on its OWN
    # session, so poll for it. `rollback()` each round ends the previous read
    # transaction -- without it a snapshot taken before the commit would be
    # re-used and the row would stay invisible however long we waited.
    # Bounded at ~2s: a real regression fails the assertion, it does not hang.
    after = None
    for _ in range(40):
        await db_session.rollback()
        after = (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.event == "user.login_failed",
                    AuditLog.target_id == user_id,
                )
            )
        ).scalars().first()
        if after is not None:
            break
        await asyncio.sleep(0.05)

    assert after is not None, (
        "a failed login must write user.login_failed to audit_log -- "
        "_audit_login_failure is a background task that swallows its own "
        "errors, so a silent regression here produces no other symptom"
    )
    assert after.data.get("reason") == "wrong_password"


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
    """Login with is_active=False -> 403, not the generic 401.

    Deliberately distinct from wrong-password/unknown-email (both 401,
    both the generic "Invalid email or password"): this branch is only
    reachable AFTER the real password already verified, so only the
    account's own holder can ever see it -- confirming "blocked" here
    costs no enumeration protection a password-guessing attacker could
    exploit. See auth/service.py's login_email is_active branch.
    """
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
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"] == "account_blocked"
    assert "suspended" in body["message"].lower()


@pytest.mark.asyncio
async def test_login_self_deactivated_user(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """TASK-38: is_active=False + credentials.account.deactivated_by="self"
    -> 403 with a DIFFERENT code/message than test_login_blocked_user's
    staff-block branch above.

    Reusing is_active=False as a bare flag (staff's block_user() shape)
    without this discriminator would tell a user who deactivated their
    OWN account that they were "suspended" -- wrong and alarming. This
    pins the login_email() branch that reads
    credentials.account.deactivated_by and picks the honest copy.

    The row is written directly here (bypassing POST /users/me/deactivate)
    so this test exercises ONLY the login-side branch -- the deactivate
    endpoint itself is covered in test_users_deactivate.py.
    """
    email = f"selfdeact_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    updated_creds = dict(user.credentials)
    updated_creds["account"] = {"deactivated_by": "self"}
    user.set_jsonb("credentials", updated_creds)
    user.is_active = False
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "testpass123"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"] == "account_self_deactivated"
    assert body["error"] != "account_blocked"
    assert "suspended" not in body["message"].lower()
    assert "deactivated" in body["message"].lower()


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


# ---------------------------------------------------------------------------
# Active sessions (TASK-38)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_marks_current(client: AsyncClient) -> None:
    """GET /sessions returns both sessions, newest first, is_current
    correctly marking only the one whose token made the request.

    Also asserts the response never contains a `token` or
    `session_token` key -- the whole point of the public session_id
    mechanism (auth/service.py's "PUBLIC SESSION ID" note) is that a
    live bearer token must never appear in this body.
    """
    email = f"s11_sesslist_{uuid.uuid4().hex[:12]}@example.com"
    password = "testpass123"

    data1 = await register_user(client, email=email, password=password)
    token1 = data1["session_token"]
    data2 = await login_user(client, email=email, password=password)
    token2 = data2["session_token"]

    resp = await client.get("/api/v1/auth/sessions", headers=auth_headers(token2))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    items = body["items"]
    assert len(items) == 2

    for item in items:
        assert "token" not in item
        assert "session_token" not in item
        assert set(item.keys()) == {
            "session_id",
            "created_at",
            "auth_method",
            "ip",
            "user_agent",
            "is_current",
        }

    # Newest-first: session #2 (this request's own token) is items[0].
    assert items[0]["is_current"] is True
    assert items[1]["is_current"] is False
    assert items[0]["auth_method"] == "email"

    # Exactly one item is marked current, and it must be session #2 --
    # asking the same endpoint with token1 flips which one that is.
    resp1 = await client.get("/api/v1/auth/sessions", headers=auth_headers(token1))
    body1 = resp1.json()
    current_ids = [i["session_id"] for i in body1["items"] if i["is_current"]]
    assert len(current_ids) == 1

    current_ids_2 = [i["session_id"] for i in items if i["is_current"]]
    # The two requests were made with different tokens -- their "current"
    # session_id must differ (each token hashes to a distinct public id).
    assert current_ids != current_ids_2


@pytest.mark.asyncio
async def test_revoke_session_kills_target_not_current(client: AsyncClient) -> None:
    """DELETE /sessions/{id} kills exactly the targeted session --
    the caller's own (current) session survives, and a subsequent
    authenticated request with the revoked token gets 401.
    """
    email = f"s11_revoke_{uuid.uuid4().hex[:12]}@example.com"
    password = "testpass123"

    data1 = await register_user(client, email=email, password=password)
    token1 = data1["session_token"]
    data2 = await login_user(client, email=email, password=password)
    token2 = data2["session_token"]

    # List via token1 -- find the OTHER session's public id (is_current=False).
    resp = await client.get("/api/v1/auth/sessions", headers=auth_headers(token1))
    assert resp.status_code == 200
    other = next(i for i in resp.json()["items"] if not i["is_current"])

    # Revoke it.
    resp = await client.delete(
        f"/api/v1/auth/sessions/{other['session_id']}",
        headers=auth_headers(token1),
    )
    assert resp.status_code == 204

    # token2 (the revoked one) is now dead.
    resp = await client.post("/api/v1/auth/logout", headers=auth_headers(token2))
    assert resp.status_code == 401

    # token1 (caller's own session) survived the revoke of the OTHER one.
    resp = await client.get("/api/v1/auth/sessions", headers=auth_headers(token1))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["is_current"] is True


@pytest.mark.asyncio
async def test_revoke_session_nonexistent_and_foreign_id_404(client: AsyncClient) -> None:
    """DELETE /sessions/{id} 404s on a made-up id AND on a real id that
    belongs to a DIFFERENT user -- never distinguishing the two (same
    "don't confirm what you can't prove the caller owns" discipline as
    the router docstring).
    """
    data_a = await register_user(client)
    token_a = data_a["session_token"]

    # A syntactically-plausible but nonexistent session_id (64 hex
    # chars, matching the SHA-256 hex digest shape).
    resp = await client.delete(
        f"/api/v1/auth/sessions/{'0' * 64}",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 404

    # A real session_id -- but belonging to user B, not user A.
    data_b = await register_user(client)
    token_b = data_b["session_token"]
    resp = await client.get("/api/v1/auth/sessions", headers=auth_headers(token_b))
    b_session_id = resp.json()["items"][0]["session_id"]

    resp = await client.delete(
        f"/api/v1/auth/sessions/{b_session_id}",
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 404

    # User B's session is untouched by A's failed attempt.
    resp = await client.get("/api/v1/auth/sessions", headers=auth_headers(token_b))
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
