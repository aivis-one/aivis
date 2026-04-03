# =============================================================================
# CBSHOME Backend -- Staff Management Tests (Sprint 3.1)
# =============================================================================
#
# Tests cover:
#   1:  Create staff user -> 201, role=staff, default permissions
#   2:  Create staff with custom permissions -> 201, overrides applied
#   3:  Create staff duplicate email -> 409
#   4:  List staff users -> includes created staff with resolved perms
#   5:  Update permissions -> PATCH changes specific keys
#   6:  Update permissions unknown key -> 422
#   7:  require_staff_permission blocks when permission is false
#   8:  Non-staff cannot access staff endpoints -> 403
#
# Email prefix: "s31_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_STAFF_PERMISSIONS
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_staff_user,
    register_user,
)

EMAIL_PREFIX = "s31_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _get_staff_token(
    client: AsyncClient, db_session: AsyncSession, suffix: str = "admin",
) -> str:
    """Helper: create and return a staff user's session token."""
    _, token = await create_staff_user(
        client, db_session, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return token


# ---------------------------------------------------------------------------
# Create staff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_staff_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/users -> 201, role=staff, default permissions resolved."""
    admin_token = await _get_staff_token(client, db_session, suffix="creator")

    resp = await client.post(
        "/api/v1/staff/users",
        json={
            "email": f"{EMAIL_PREFIX}new@example.com",
            "password": "strongpass1",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    body = resp.json()

    assert body["role"] == "staff"
    assert body["is_active"] is True
    assert body["email"] == f"{EMAIL_PREFIX}new@example.com"
    assert "staff_profile_id" in body
    assert "permissions" in body

    # Verify all default permissions are resolved.
    for key, default_val in DEFAULT_STAFF_PERMISSIONS.items():
        assert body["permissions"][key] == default_val, (
            f"Permission '{key}' should be {default_val}"
        )


@pytest.mark.asyncio
async def test_create_staff_with_custom_permissions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/users with permission overrides -> 201, overrides applied."""
    admin_token = await _get_staff_token(client, db_session, suffix="creator2")

    resp = await client.post(
        "/api/v1/staff/users",
        json={
            "email": f"{EMAIL_PREFIX}support@example.com",
            "password": "strongpass1",
            "permissions": {
                "financial_operations": False,
                "translation_edit": True,
            },
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    body = resp.json()

    # Overrides applied.
    assert body["permissions"]["financial_operations"] is False
    assert body["permissions"]["translation_edit"] is True

    # Defaults preserved for non-overridden keys.
    assert body["permissions"]["avatar_mode"] is True
    assert body["permissions"]["kyc_approve"] is True


@pytest.mark.asyncio
async def test_create_staff_duplicate_email(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /staff/users with existing email -> 409."""
    admin_token = await _get_staff_token(client, db_session, suffix="creator3")

    email = f"{EMAIL_PREFIX}dup@example.com"

    # First creation succeeds.
    resp1 = await client.post(
        "/api/v1/staff/users",
        json={"email": email, "password": "strongpass1"},
        headers=auth_headers(admin_token),
    )
    assert resp1.status_code == 201

    # Second creation with same email -> 409.
    resp2 = await client.post(
        "/api/v1/staff/users",
        json={"email": email, "password": "strongpass1"},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# List staff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_staff_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /staff/users -> list includes created staff with resolved perms."""
    admin_token = await _get_staff_token(client, db_session, suffix="lister")

    # Create another staff user via API.
    await client.post(
        "/api/v1/staff/users",
        json={
            "email": f"{EMAIL_PREFIX}listed@example.com",
            "password": "strongpass1",
        },
        headers=auth_headers(admin_token),
    )

    resp = await client.get(
        "/api/v1/staff/users",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    # At least the admin and the newly created staff.
    assert len(body) >= 2

    emails = [item["email"] for item in body]
    assert f"{EMAIL_PREFIX}listed@example.com" in emails

    # Each item has resolved permissions.
    for item in body:
        assert "permissions" in item
        assert "avatar_mode" in item["permissions"]


# ---------------------------------------------------------------------------
# Update permissions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_permissions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH /staff/users/{id}/permissions -> updates specific keys."""
    admin_token = await _get_staff_token(client, db_session, suffix="updater")

    # Create target staff.
    resp_create = await client.post(
        "/api/v1/staff/users",
        json={
            "email": f"{EMAIL_PREFIX}target@example.com",
            "password": "strongpass1",
        },
        headers=auth_headers(admin_token),
    )
    target_id = resp_create.json()["id"]

    # Update permissions.
    resp = await client.patch(
        f"/api/v1/staff/users/{target_id}/permissions",
        json={"permissions": {"financial_operations": False}},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["permissions"]["financial_operations"] is False
    # Other keys unchanged.
    assert body["permissions"]["avatar_mode"] is True


@pytest.mark.asyncio
async def test_update_permissions_unknown_key(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH /staff/users/{id}/permissions with unknown key -> 422."""
    admin_token = await _get_staff_token(client, db_session, suffix="updater2")

    # Create target staff.
    resp_create = await client.post(
        "/api/v1/staff/users",
        json={
            "email": f"{EMAIL_PREFIX}target2@example.com",
            "password": "strongpass1",
        },
        headers=auth_headers(admin_token),
    )
    target_id = resp_create.json()["id"]

    resp = await client.patch(
        f"/api/v1/staff/users/{target_id}/permissions",
        json={"permissions": {"nonexistent_perm": True}},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Permission dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_staff_permission_blocks() -> None:
    """_has_permission correctly resolves defaults + overrides.

    Uses SimpleNamespace to avoid SQLAlchemy _sa_instance_state issue
    with StaffProfile.__new__().
    """
    from app.modules.auth.dependencies import _has_permission

    # Profile with financial_operations overridden to False.
    profile_denied = SimpleNamespace(permissions={"financial_operations": False})
    assert _has_permission(profile_denied, "financial_operations") is False

    # Default True permission should pass (not overridden).
    assert _has_permission(profile_denied, "avatar_mode") is True

    # Default False permission (translation_edit) without override.
    profile_empty = SimpleNamespace(permissions={})
    assert _has_permission(profile_empty, "translation_edit") is False

    # Override default False to True.
    profile_override = SimpleNamespace(permissions={"translation_edit": True})
    assert _has_permission(profile_override, "translation_edit") is True


# ---------------------------------------------------------------------------
# Non-staff access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_staff_cannot_access_staff_endpoints(
    client: AsyncClient,
) -> None:
    """Investor trying staff endpoints -> 403."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}investor@example.com"
    )
    token = data["session_token"]

    # Try to list staff.
    resp = await client.get(
        "/api/v1/staff/users",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
