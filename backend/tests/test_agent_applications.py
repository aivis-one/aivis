# =============================================================================
# CBSHOME Backend -- Agent Application Tests (Sprint 7.1)
# =============================================================================
#
# Tests cover:
#   1:  Submit application -> 201, status=pending
#   2:  Submit duplicate (already pending) -> 409
#   3:  Submit non-investor -> 400
#   4:  GET /me -> 200, list with submitted application
#   5:  Staff queue -> 200, pending applications
#   6:  Staff approve -> 204, user.role = agent
#   7:  Staff reject -> 204, cooldown_until set
#   8:  Approve non-existent -> 404
#   9:  Reject without reason -> 422
#   10: Submit during cooldown -> 400
#   11: Submit after cooldown expires -> 201
#   12: Already approved user submits again -> 400 (role is agent)
#
# Email prefix: "s71_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent_applications.models import AgentApplication
from app.modules.users.models import User, UserRole
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    register_user,
)

EMAIL_PREFIX = "s71_"


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


async def _create_investor(
    client: AsyncClient, suffix: str = "inv1"
) -> tuple[UUID, str]:
    """Helper: register investor, return (user_id, token)."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return UUID(data["user"]["id"]), data["session_token"]


# ---------------------------------------------------------------------------
# 1: Submit application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_application(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /agent-applications -> 201, status=pending."""
    _, token = await _create_investor(client, "sub1")

    resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["rejection_reason"] is None
    assert body["cooldown_until"] is None


# ---------------------------------------------------------------------------
# 2: Duplicate submission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_duplicate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second submit while pending -> 409."""
    _, token = await _create_investor(client, "dup1")

    resp1 = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(token),
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# 3: Non-investor submission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_non_investor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff user submits -> 400."""
    _, token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}staff1@example.com"
    )

    resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 4: List my applications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_my_applications(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /agent-applications/me -> 200, includes submitted app."""
    _, token = await _create_investor(client, "list1")

    # Before submit -- empty.
    resp1 = await client.get(
        "/api/v1/agent-applications/me",
        headers=auth_headers(token),
    )
    assert resp1.status_code == 200
    assert resp1.json()["total"] == 0

    # Submit.
    await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(token),
    )

    # After submit -- one item.
    resp2 = await client.get(
        "/api/v1/agent-applications/me",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending"


# ---------------------------------------------------------------------------
# 5: Staff queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_queue(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /staff/agent-applications -> 200, pending applications."""
    admin_token = await _admin_token(client, db_session)
    _, inv_token = await _create_investor(client, "queue1")

    # Submit application.
    await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )

    resp = await client.get(
        "/api/v1/staff/agent-applications",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    # At least our submitted application is in the queue.
    statuses = [item["status"] for item in items]
    assert "pending" in statuses


# ---------------------------------------------------------------------------
# 6: Staff approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_approve(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approve -> 204, user.role becomes agent."""
    admin_token = await _admin_token(client, db_session)
    user_id, inv_token = await _create_investor(client, "appr1")

    # Submit.
    submit_resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    app_id = submit_resp.json()["id"]

    # Approve.
    resp = await client.post(
        f"/api/v1/staff/agent-applications/{app_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    # Verify role changed.
    me_resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(inv_token),
    )
    assert me_resp.json()["role"] == "agent"


# ---------------------------------------------------------------------------
# 7: Staff reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_reject(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reject -> 204, cooldown_until set, rejection_reason stored."""
    admin_token = await _admin_token(client, db_session)
    user_id, inv_token = await _create_investor(client, "rej1")

    # Submit.
    submit_resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    app_id = submit_resp.json()["id"]

    # Reject.
    resp = await client.post(
        f"/api/v1/staff/agent-applications/{app_id}/reject",
        json={"reason": "Insufficient experience"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    # Verify via /me.
    me_resp = await client.get(
        "/api/v1/agent-applications/me",
        headers=auth_headers(inv_token),
    )
    app = me_resp.json()["items"][0]
    assert app["status"] == "rejected"
    assert app["rejection_reason"] == "Insufficient experience"
    assert app["cooldown_until"] is not None


# ---------------------------------------------------------------------------
# 8: Approve non-existent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_nonexistent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Approve non-existent application -> 404."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{uuid4()}/approve",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 9: Reject without reason
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_without_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reject without reason body -> 422."""
    admin_token = await _admin_token(client, db_session)
    _, inv_token = await _create_investor(client, "noreason")

    submit_resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    app_id = submit_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/staff/agent-applications/{app_id}/reject",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 10: Submit during cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_during_cooldown(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Submit during cooldown -> 400."""
    admin_token = await _admin_token(client, db_session)
    user_id, inv_token = await _create_investor(client, "cool1")

    # Submit and reject.
    submit_resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    app_id = submit_resp.json()["id"]

    await client.post(
        f"/api/v1/staff/agent-applications/{app_id}/reject",
        json={"reason": "Not ready"},
        headers=auth_headers(admin_token),
    )

    # Try to submit again -> cooldown active.
    resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 400
    assert "Cooldown" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 11: Submit after cooldown expires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_after_cooldown_expires(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Submit after cooldown expires -> 201."""
    admin_token = await _admin_token(client, db_session)
    user_id, inv_token = await _create_investor(client, "cool2")

    # Submit and reject.
    submit_resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    app_id = submit_resp.json()["id"]

    await client.post(
        f"/api/v1/staff/agent-applications/{app_id}/reject",
        json={"reason": "Not ready"},
        headers=auth_headers(admin_token),
    )

    # Manually expire cooldown in DB.
    await db_session.execute(
        update(AgentApplication)
        .where(AgentApplication.id == app_id)
        .values(cooldown_until=datetime.now(UTC) - timedelta(days=1))
    )
    await db_session.commit()

    # Submit again -> should succeed.
    resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 12: Approved user submits again
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approved_user_submits_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """User who was approved (now agent) submits again -> 400."""
    admin_token = await _admin_token(client, db_session)
    user_id, inv_token = await _create_investor(client, "again1")

    # Submit and approve.
    submit_resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    app_id = submit_resp.json()["id"]

    await client.post(
        f"/api/v1/staff/agent-applications/{app_id}/approve",
        headers=auth_headers(admin_token),
    )

    # Try to submit again -> role is agent, not investor.
    resp = await client.post(
        "/api/v1/agent-applications",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 400
    assert "investor" in resp.json()["message"].lower()
