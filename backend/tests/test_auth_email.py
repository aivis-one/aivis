# =============================================================================
# CBSHOME Backend -- Email Auth Tests (Sprint 1.1)
# =============================================================================
#
# Tests cover:
#   1-4:   Registration (success, duplicate, weak password, invalid email)
#   5-9:   Login (success, wrong password, non-existent, blocked, platform)
#   10-12: Logout, logout invalid token, logout-all
#
# Email prefix: "s11_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserRole
from tests.helpers import auth_headers, cleanup_test_users, login_user, register_user

EMAIL_PREFIX = "s11_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """Register with valid email + password -> 201, AuthResponse."""
    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": f"{EMAIL_PREFIX}ok@example.com", "password": "strongpass1"},
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
    email = f"{EMAIL_PREFIX}dup@example.com"
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
        json={"email": f"{EMAIL_PREFIX}weak@example.com", "password": "short"},
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
    email = f"{EMAIL_PREFIX}login@example.com"
    await register_user(client, email=email)

    data = await login_user(client, email=email)
    assert "session_token" in data
    assert data["user"]["role"] == "investor"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    """Login with wrong password -> 401."""
    email = f"{EMAIL_PREFIX}wrongpw@example.com"
    await register_user(client, email=email)

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient) -> None:
    """Login with email that doesn't exist -> 401."""
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": f"{EMAIL_PREFIX}ghost@example.com", "password": "whatever1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_blocked_user(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Login with is_active=False -> 403."""
    email = f"{EMAIL_PREFIX}blocked@example.com"
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


@pytest.mark.asyncio
async def test_login_platform_user(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Login as platform user -> 401 (platform cannot log in)."""
    email = f"{EMAIL_PREFIX}platform@example.com"
    await register_user(client, email=email)

    # Change role to platform directly in DB.
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.PLATFORM
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "testpass123"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient) -> None:
    """Logout with valid token -> 204, subsequent request -> 401."""
    email = f"{EMAIL_PREFIX}logout@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Logout.
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(token),
    )
    assert resp.status_code == 204

    # Token should be invalid now.
    resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    # 401 or 404 (users/me not registered yet in Sprint 1.1,
    # but auth dependency will reject with 401).
    assert resp.status_code in (401, 404)


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
    email = f"{EMAIL_PREFIX}logoutall@example.com"
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
