# =============================================================================
# CBSHOME Backend -- User Profile Tests (Sprint 1.3)
# =============================================================================
#
# Tests cover:
#   1-3:  GET /me (success, no auth, invalid token)
#   4-7:  PATCH /me (profile update, language, partial, empty body)
#   8:    PATCH /me no auth -> 401
#   9:    GET /me blocked user -> 403
#   10:   Avatar guard blocks restricted operation -> 403
#
# Email prefix: "s13_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator

import pytest
import structlog
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import auth_headers, cleanup_test_users, register_user


EMAIL_PREFIX = "s13_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# GET /api/v1/users/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_success(client: AsyncClient) -> None:
    """Authenticated user can retrieve their profile."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}me@example.com")
    token = data["session_token"]

    resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["role"] == "investor"
    assert body["is_active"] is True
    assert body["onboarding_step"] == "registered"
    assert body["kyc_status"] == "not_started"
    assert body["language"] == "en"
    assert "id" in body
    assert "created_at" in body
    # credentials must NOT be exposed
    assert "credentials" not in body


@pytest.mark.asyncio
async def test_get_me_no_auth(client: AsyncClient) -> None:
    """Request without token -> 401."""
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(client: AsyncClient) -> None:
    """Request with garbage token -> 401."""
    resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers("garbage-token"),
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_me_update_profile(client: AsyncClient) -> None:
    """Update profile.first_name -> 200, value persisted."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}patch1@example.com")
    token = data["session_token"]

    resp = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers(token),
        json={"profile": {"first_name": "Alice", "country": "DE"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["first_name"] == "Alice"
    assert body["profile"]["country"] == "DE"

    # Verify persistence via GET.
    get_resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert get_resp.json()["profile"]["first_name"] == "Alice"


@pytest.mark.asyncio
async def test_patch_me_update_language(client: AsyncClient) -> None:
    """Update language -> 200, value persisted."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}patch2@example.com")
    token = data["session_token"]

    resp = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers(token),
        json={"language": "de"},
    )
    assert resp.status_code == 200
    assert resp.json()["language"] == "de"


@pytest.mark.asyncio
async def test_patch_me_partial_update(client: AsyncClient) -> None:
    """Update only language -- profile unchanged."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}patch3@example.com")
    token = data["session_token"]

    # Set profile first.
    await client.patch(
        "/api/v1/users/me",
        headers=auth_headers(token),
        json={"profile": {"first_name": "Bob"}},
    )

    # Update only language -- profile should stay.
    resp = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers(token),
        json={"language": "ru"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["language"] == "ru"
    assert body["profile"]["first_name"] == "Bob"


@pytest.mark.asyncio
async def test_patch_me_empty_body(client: AsyncClient) -> None:
    """Empty body -> 200, no changes."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}patch4@example.com")
    token = data["session_token"]

    resp = await client.patch(
        "/api/v1/users/me",
        headers=auth_headers(token),
        json={},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_patch_me_no_auth(client: AsyncClient) -> None:
    """PATCH without token -> 401."""
    resp = await client.patch(
        "/api/v1/users/me",
        json={"language": "de"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_me_blocked_user(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /me with is_active=False -> 403."""
    from sqlalchemy import select
    from app.modules.users.models import User

    email = f"{EMAIL_PREFIX}blocked@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    # Deactivate directly in DB.
    stmt = select(User).where(
        User.credentials["email"]["email"].as_string() == email
    )
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Avatar guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_avatar_guard_blocks_restricted_operation() -> None:
    """require_not_avatar blocks when avatar_session_id is in contextvars.

    Simulates avatar mode by manually binding avatar_session_id
    to structlog contextvars (same mechanism Sprint 3.2 will use).
    """
    from app.modules.auth.avatar_guard import require_not_avatar
    from app.core.exceptions import ForbiddenError

    # Define a dummy restricted endpoint.
    @require_not_avatar("create_payment")
    async def dummy_create_payment() -> str:
        return "ok"

    # Without avatar -- should pass.
    structlog.contextvars.clear_contextvars()
    result = await dummy_create_payment()
    assert result == "ok"

    # With avatar -- should raise ForbiddenError.
    structlog.contextvars.bind_contextvars(avatar_session_id="test-avatar-123")
    with pytest.raises(ForbiddenError, match="not allowed in avatar mode"):
        await dummy_create_payment()

    # Cleanup.
    structlog.contextvars.clear_contextvars()
