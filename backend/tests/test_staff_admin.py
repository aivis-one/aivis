# =============================================================================
# CBSHOME Backend -- Staff Admin Tests (Sprint 3.3)
# =============================================================================
#
# Tests cover:
#   1:  List users -> 200, paginated, platform excluded
#   2:  List users ?role=staff -> only staff with permissions
#   3:  List users ?role=investor -> only investors, no staff_profile
#   4:  Get user detail -> 200, full info
#   5:  Get platform user detail -> 404
#   6:  Block investor -> 204, is_active=false, sessions killed
#   7:  Block staff user -> 400
#   8:  Dashboard stats -> 200, correct counts
#   9:  KYC queue -> 200, pending applications with user info
#   10: KYC approve -> 204, status updated
#   11: KYC reject -> 204, status updated
#   12: KYC approve non-existent -> 404
#
# Email prefix: "s33_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserRole
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s33_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}admin@example.com"
    )
    return token


# ---------------------------------------------------------------------------
# GET /staff/users -- unified user list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_paginated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """List users -> 200, paginated response, platform excluded."""
    admin_token = await _admin_token(client, db_session)

    # Create a few investors.
    await register_user(client, email=f"{EMAIL_PREFIX}inv1@example.com")
    await register_user(client, email=f"{EMAIL_PREFIX}inv2@example.com")

    resp = await client.get(
        "/api/v1/staff/users?page=1&per_page=50",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert body["page"] == 1

    # Platform user should not appear.
    roles = [item["role"] for item in body["items"]]
    assert "platform" not in roles


@pytest.mark.asyncio
async def test_list_users_filter_staff(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """List users ?role=staff -> only staff with staff_profile."""
    admin_token = await _admin_token(client, db_session)

    # Create an investor (should not appear).
    await register_user(client, email=f"{EMAIL_PREFIX}inv3@example.com")

    resp = await client.get(
        "/api/v1/staff/users?role=staff",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    # All items are staff.
    for item in body["items"]:
        assert item["role"] == "staff"
        assert item["staff_profile"] is not None
        assert "permissions" in item["staff_profile"]


@pytest.mark.asyncio
async def test_list_users_filter_investor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """List users ?role=investor -> investors, no staff_profile."""
    admin_token = await _admin_token(client, db_session)
    await register_user(client, email=f"{EMAIL_PREFIX}inv4@example.com")

    resp = await client.get(
        "/api/v1/staff/users?role=investor",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()

    for item in body["items"]:
        assert item["role"] == "investor"
        assert item["staff_profile"] is None


# ---------------------------------------------------------------------------
# GET /staff/users/{id} -- user detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_detail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get user detail -> 200, full info."""
    admin_token = await _admin_token(client, db_session)
    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}detail@example.com"
    )
    user_id = inv_data["user"]["id"]

    resp = await client.get(
        f"/api/v1/staff/users/{user_id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == user_id
    assert body["role"] == "investor"
    assert "profile" in body
    assert "kyc_status" in body


@pytest.mark.asyncio
async def test_get_platform_user_hidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get platform user detail -> 404 (hidden)."""
    admin_token = await _admin_token(client, db_session)

    # Find platform user.
    stmt = select(User).where(User.role == UserRole.PLATFORM)
    result = await db_session.execute(stmt)
    platform = result.scalar_one_or_none()

    if platform is None:
        pytest.skip("No platform user in DB")

    resp = await client.get(
        f"/api/v1/staff/users/{platform.id}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /staff/users/{id}/block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_block_investor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Block investor -> 204, is_active=false, can't auth anymore."""
    admin_token = await _admin_token(client, db_session)
    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}block@example.com"
    )
    user_id = inv_data["user"]["id"]
    inv_token = inv_data["session_token"]

    # Block.
    resp = await client.patch(
        f"/api/v1/staff/users/{user_id}/block",
        json={"reason": "test block"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    # Investor's session should be killed.
    me_resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(inv_token),
    )
    assert me_resp.status_code == 401


@pytest.mark.asyncio
async def test_block_staff_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Block staff user -> 400."""
    admin_token = await _admin_token(client, db_session)

    # Create another staff.
    other_data = await register_user(
        client, email=f"{EMAIL_PREFIX}otherstaff@example.com"
    )
    await client.post(
        "/api/v1/staff/users",
        json={"user_id": other_data["user"]["id"]},
        headers=auth_headers(admin_token),
    )

    # Try to block -> 400.
    resp = await client.patch(
        f"/api/v1/staff/users/{other_data['user']['id']}/block",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /staff/dashboard/stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_stats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dashboard stats -> 200, correct structure."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.get(
        "/api/v1/staff/dashboard/stats",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total_users" in body
    assert "users_by_role" in body
    assert "pending_kyc_count" in body
    assert "active_avatar_sessions" in body
    assert body["total_users"] >= 1


# ---------------------------------------------------------------------------
# KYC queue + approve/reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kyc_queue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """KYC queue -> 200, pending applications with user info."""
    admin_token = await _admin_token(client, db_session)

    # Create investor and submit KYC.
    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}kyc1@example.com"
    )
    inv_token = inv_data["session_token"]
    await client.post("/api/v1/kyc/submit", headers=auth_headers(inv_token))

    resp = await client.get(
        "/api/v1/staff/kyc/queue",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1

    item = body[-1]  # Last submitted.
    assert item["status"] == "submitted"
    assert "email" in item
    assert "user_id" in item


@pytest.mark.asyncio
async def test_kyc_approve(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approve KYC -> 204, user kyc_status updated."""
    admin_token = await _admin_token(client, db_session)

    # Create investor and submit KYC.
    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}kyc2@example.com"
    )
    inv_token = inv_data["session_token"]
    submit_resp = await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(inv_token)
    )
    application_id = submit_resp.json()["id"]

    # Approve.
    resp = await client.post(
        f"/api/v1/staff/kyc/{application_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    # Verify user kyc_status.
    me_resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(inv_token),
    )
    assert me_resp.json()["kyc_status"] == "approved"


@pytest.mark.asyncio
async def test_kyc_reject(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reject KYC -> 204, user kyc_status updated."""
    admin_token = await _admin_token(client, db_session)

    inv_data = await register_user(
        client, email=f"{EMAIL_PREFIX}kyc3@example.com"
    )
    inv_token = inv_data["session_token"]
    submit_resp = await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(inv_token)
    )
    application_id = submit_resp.json()["id"]

    # Reject.
    resp = await client.post(
        f"/api/v1/staff/kyc/{application_id}/reject",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    me_resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(inv_token),
    )
    assert me_resp.json()["kyc_status"] == "rejected"


@pytest.mark.asyncio
async def test_kyc_approve_nonexistent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approve non-existent KYC application -> 404."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        f"/api/v1/staff/kyc/{uuid4()}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404
