# =============================================================================
# CBSHOME Backend -- Staff Tests (Sprint 3.1 + 3.3)
# =============================================================================
#
# Tests cover:
#   1:  Admin promotes user to staff -> 201
#   2:  Non-admin promotes user -> 403
#   3:  Promote platform user -> 400
#   4:  Promote already-staff user -> 409
#   5:  Update permissions -> 200, partial update works
#   6:  Non-admin updates permissions -> 403
#   7:  List users -> 200, paginated, staff have staff_profile
#   8:  Promote non-existent user -> 404
#
# Email prefix: "s31_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.staff.constants import VALID_PERMISSION_KEYS
from app.modules.staff.models import StaffProfile
from app.modules.users.models import User, UserRole
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s31_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create and return an admin user's session token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


async def _register_investor(
    client: AsyncClient,
    email: str | None = None,
) -> dict:
    """Helper: register an investor and return response data."""
    email = email or f"{EMAIL_PREFIX}investor@example.com"
    return await register_user(client, email=email)


# ---------------------------------------------------------------------------
# POST /staff/users -- promote user to staff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_user_to_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admin promotes investor to staff -> 201."""
    admin_token = await _admin_token(client, db_session)
    investor_data = await _register_investor(client)
    investor_id = investor_data["user"]["id"]

    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user_id"] == investor_id
    assert body["is_active"] is True
    assert "permissions" in body

    # Verify role changed in DB.
    stmt = select(User).where(User.id == investor_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    assert user.role == UserRole.STAFF


@pytest.mark.asyncio
async def test_promote_non_admin_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Non-admin staff cannot promote users -> 403."""
    # Create admin first, then create a regular staff via admin.
    admin_token = await _admin_token(client, db_session)
    regular_data = await register_user(
        client, email=f"{EMAIL_PREFIX}regular@example.com"
    )
    regular_id = regular_data["user"]["id"]

    # Admin promotes regular to staff.
    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": regular_id},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    staff_profile = resp.json()

    # Remove one permission to make them non-admin.
    resp2 = await client.patch(
        f"/api/v1/staff/users/{staff_profile['id']}/permissions",
        json={"translation_edit": False},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 200

    # Regular staff re-login.
    from tests.helpers import login_user
    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}regular@example.com"
    )
    regular_token = login_data["session_token"]

    # Try to promote another user -- should fail.
    another = await register_user(
        client, email=f"{EMAIL_PREFIX}another@example.com"
    )
    resp3 = await client.post(
        "/api/v1/staff/users",
        json={"user_id": another["user"]["id"]},
        headers=auth_headers(regular_token),
    )
    assert resp3.status_code == 403


@pytest.mark.asyncio
async def test_promote_platform_user_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cannot promote platform user -> 400."""
    admin_token = await _admin_token(client, db_session)

    # Find platform user.
    stmt = select(User).where(User.role == UserRole.PLATFORM)
    result = await db_session.execute(stmt)
    platform = result.scalar_one_or_none()

    if platform is None:
        pytest.skip("No platform user in DB")

    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": str(platform.id)},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_promote_already_staff_conflict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Promoting already-staff user -> 409."""
    admin_token = await _admin_token(client, db_session)
    investor_data = await _register_investor(
        client, email=f"{EMAIL_PREFIX}dup@example.com"
    )
    investor_id = investor_data["user"]["id"]

    # First promotion -- success.
    resp1 = await client.post(
        "/api/v1/staff/users",
        json={"user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert resp1.status_code == 201

    # Second promotion -- conflict.
    resp2 = await client.post(
        "/api/v1/staff/users",
        json={"user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# PATCH /staff/users/{id}/permissions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_permissions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admin updates staff permissions -> 200, partial update."""
    admin_token = await _admin_token(client, db_session)
    investor_data = await _register_investor(
        client, email=f"{EMAIL_PREFIX}perm@example.com"
    )
    investor_id = investor_data["user"]["id"]

    # Promote to staff.
    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    profile_id = resp.json()["id"]

    # Update one permission.
    resp2 = await client.patch(
        f"/api/v1/staff/users/{profile_id}/permissions",
        json={"financial_operations": False},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["permissions"]["financial_operations"] is False
    # Other defaults remain.
    assert body["permissions"]["kyc_approve"] is True


@pytest.mark.asyncio
async def test_update_permissions_non_admin_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Non-admin cannot update permissions -> 403."""
    admin_token = await _admin_token(client, db_session)

    # Create a regular staff.
    regular_data = await register_user(
        client, email=f"{EMAIL_PREFIX}nonadm@example.com"
    )
    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": regular_data["user"]["id"]},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    profile_id = resp.json()["id"]

    # Downgrade to non-admin.
    await client.patch(
        f"/api/v1/staff/users/{profile_id}/permissions",
        json={"translation_edit": False},
        headers=auth_headers(admin_token),
    )

    # Re-login as regular staff.
    from tests.helpers import login_user
    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}nonadm@example.com"
    )
    regular_token = login_data["session_token"]

    # Try to update own permissions.
    resp2 = await client.patch(
        f"/api/v1/staff/users/{profile_id}/permissions",
        json={"financial_operations": True},
        headers=auth_headers(regular_token),
    )
    assert resp2.status_code == 403


# ---------------------------------------------------------------------------
# GET /staff/users -- unified user list (Sprint 3.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff can list users -> 200, paginated, staff have staff_profile."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.get(
        "/api/v1/staff/users",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    # Paginated response.
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "per_page" in body
    assert body["total"] >= 1

    # At least the admin should be in the list.
    staff_items = [i for i in body["items"] if i["role"] == "staff"]
    assert len(staff_items) >= 1

    # Staff items have staff_profile with permissions.
    for item in staff_items:
        assert item["staff_profile"] is not None
        assert "permissions" in item["staff_profile"]


# ---------------------------------------------------------------------------
# Edge case: non-existent user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promote_nonexistent_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Promote non-existent user -> 404."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": str(uuid4())},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404
