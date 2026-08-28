# =============================================================================
# AIVIS.ONE Backend -- Self-Deactivation Tests (TASK-38)
# =============================================================================
#
# Tests cover:
#   1: Happy path -- deactivate -> 204, is_active=False, discriminator
#      set, every session killed (including the caller's own), login
#      afterward gets the SELF-deactivated message (not "suspended")
#   2: Wrong current password -> 403 incorrect_password, account stays
#      active, existing session still works
#   3: Every session is killed, not just the caller's -- a SECOND
#      session (different login) also dies
#   4: Audit event user.self_deactivated, actor_type="user"
#   5: Staff cannot self-deactivate via this endpoint -> 400
#
# Email prefix: "deact_" -- unique to this test file.
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.modules.users.models import User
from tests.helpers import auth_headers, create_staff_user, login_user, register_user

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_happy_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deactivate -> 204; the caller's own token dies with the session
    kill, and a subsequent login attempt gets the SELF-deactivated
    message (not the staff-block "suspended" copy).
    """
    email = f"deact_happy_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": password},
        headers=auth_headers(token),
    )
    assert resp.status_code == 204, resp.text

    # The caller's own session died as part of the kill-all.
    me_resp = await client.get("/api/v1/users/me", headers=auth_headers(token))
    assert me_resp.status_code == 401

    # DB state: is_active False, discriminator set to self.
    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    assert user.is_active is False
    assert user.credentials.get("account", {}).get("deactivated_by") == "self"

    # Login afterward -> 403, the SELF-deactivated message, not
    # test_login_blocked_user's "suspended" copy.
    login_resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 403
    body = login_resp.json()
    assert body["error"] == "account_self_deactivated"
    assert "suspended" not in body["message"].lower()


# ---------------------------------------------------------------------------
# Re-authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_wrong_current_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Wrong current_password -> 403 incorrect_password; the account
    stays active and the caller's OWN session survives (nothing was
    torn down by a failed re-auth attempt).
    """
    email = f"deact_wrongpw_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": "definitely-not-it"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "incorrect_password"

    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    assert user.is_active is True

    # The session that made the failed attempt is still alive.
    me_resp = await client.get("/api/v1/users/me", headers=auth_headers(token))
    assert me_resp.status_code == 200


# ---------------------------------------------------------------------------
# Session kill scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_kills_every_session_not_just_the_caller(
    client: AsyncClient,
) -> None:
    """A SECOND session (a separate login, e.g. another device) also
    dies -- not only the token that made the deactivate call.
    """
    email = f"deact_multisession_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token_a = data["session_token"]

    other_login = await login_user(client, email=email, password=password)
    token_b = other_login["session_token"]
    assert token_b != token_a

    resp = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": password},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 204, resp.text

    resp_b = await client.get("/api/v1/users/me", headers=auth_headers(token_b))
    assert resp_b.status_code == 401, (
        "deactivate must kill EVERY session, not only the caller's own"
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_writes_audit_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A `user.self_deactivated` row lands in audit_log with
    actor_type="user" -- distinct from staff's `user.blocked`
    (actor_type="staff"), so the two are never confused in review.
    """
    email = f"deact_audit_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]
    user_id = data["user"]["id"]

    resp = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": password},
        headers=auth_headers(token),
    )
    assert resp.status_code == 204, resp.text

    await db_session.rollback()
    row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.event == "user.self_deactivated",
                AuditLog.target_id == uuid.UUID(user_id),
            )
        )
    ).scalars().first()
    assert row is not None
    assert row.actor_type == "user"
    assert row.actor_id == uuid.UUID(user_id)


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_cannot_self_deactivate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A staff account calling this endpoint on itself -> 400.

    Mirrors block_user()'s "Cannot block staff user" guard -- staff
    accounts are trusted operational accounts, not meant to be able to
    silently lock themselves out through the same self-service path an
    investor uses.
    """
    staff_user, staff_token = await create_staff_user(client, db_session)

    resp = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": "Password123!"},
        headers=auth_headers(staff_token),
    )
    assert resp.status_code == 400

    await db_session.refresh(staff_user)
    assert staff_user.is_active is True
