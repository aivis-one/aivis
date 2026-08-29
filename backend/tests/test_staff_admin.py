# =============================================================================
# AIVIS.ONE Backend -- Staff Admin Tests (Sprint 3.3, iter 2.6c B1)
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
#   8b: Dashboard stats frozen_payments_count -> moves by +1 when a FROZEN
#       payment is seeded (shared-DB safe: delta, not absolute count)
#   9:  KYC queue -> 200, pending applications with user info
#   10: KYC approve -> 204, status updated
#   11: KYC reject -> 204, status updated
#   12: KYC approve non-existent -> 404
#   13: (B1) ?kyc_status= positive-and-negative pair across 4 enum values
#   14: (B1) ?role=investor combined with ?kyc_status=approved
#   15: (B1) ?kyc_status=garbage -> 422 from the FastAPI enum bind
#
# Email prefix: "s33_" -- unique to this test file, cleaned up in fixture.
#
# iter 2.6c B1 NOTES:
#   The dev DB is shared (see conftest.py) and accumulates rows across
#   runs. We never iterate over the returned items to assert every one
#   has the requested kyc_status -- that would either succeed
#   tautologically when the SQL clause works or fail noisily on
#   pre-existing pollution. Instead, each B1 test materialises a
#   freshly registered investor in a known kyc_status, then runs two
#   probes:
#     * positive: ?kyc_status=<expected> must return that investor
#     * negative: ?kyc_status=<other>    must NOT return that investor
#   The pair is robust against arbitrary pre-existing rows and is the
#   only configuration that actually exercises the new WHERE clause.
# =============================================================================

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.constants import PaymentStatus, PaymentType
from app.modules.payments.models import Payment
from app.modules.users.models import User, UserRole
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)



async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(
        client, db_session
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
    await register_user(client)
    await register_user(client)

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
    await register_user(client)

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
    await register_user(client)

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
        client
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
        client
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
        client
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
# PATCH /staff/users/{id}/unblock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unblock_investor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unblock a blocked investor -> 204, is_active=true, can log in again."""
    admin_token = await _admin_token(client, db_session)
    inv_data = await register_user(client)
    user_id = inv_data["user"]["id"]

    # Block first.
    block_resp = await client.patch(
        f"/api/v1/staff/users/{user_id}/block",
        json={"reason": "test block"},
        headers=auth_headers(admin_token),
    )
    assert block_resp.status_code == 204

    detail_resp = await client.get(
        f"/api/v1/staff/users/{user_id}",
        headers=auth_headers(admin_token),
    )
    assert detail_resp.json()["is_active"] is False

    # Unblock.
    unblock_resp = await client.patch(
        f"/api/v1/staff/users/{user_id}/unblock",
        headers=auth_headers(admin_token),
    )
    assert unblock_resp.status_code == 204

    # is_active flips back to true.
    detail_resp = await client.get(
        f"/api/v1/staff/users/{user_id}",
        headers=auth_headers(admin_token),
    )
    assert detail_resp.json()["is_active"] is True

    # The user can authenticate again (a fresh login succeeds -- the
    # is_active gate other code checks no longer refuses them). The
    # old session_token was already killed by block and stays dead;
    # what matters is is_active no longer blocks a *new* login.
    login_resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": inv_data["email"], "password": "Password123!"},
    )
    assert login_resp.status_code == 200, login_resp.text


@pytest.mark.asyncio
async def test_unblock_already_active_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unblocking a user who was never blocked -> 204, no-op success.

    Mirrors block_user's own precedent: block_user has no "already
    blocked" guard (it unconditionally sets is_active=False), so
    unblock_user unconditionally sets is_active=True with no "already
    active" guard either.
    """
    admin_token = await _admin_token(client, db_session)
    inv_data = await register_user(client)
    user_id = inv_data["user"]["id"]

    resp = await client.patch(
        f"/api/v1/staff/users/{user_id}/unblock",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204

    detail_resp = await client.get(
        f"/api/v1/staff/users/{user_id}",
        headers=auth_headers(admin_token),
    )
    assert detail_resp.json()["is_active"] is True


@pytest.mark.asyncio
async def test_unblock_nonexistent_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Unblock a non-existent user -> 404."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.patch(
        f"/api/v1/staff/users/{uuid4()}/unblock",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unblock_requires_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A non-staff caller is refused /unblock -> 403.

    Mirrors test_agent_applications.py's test_non_staff_cannot_reach_queue:
    an ordinary investor has no staff permissions at all, so
    require_staff_permission("user_block") refuses them the same way
    it would refuse a staff member without the user_block permission
    specifically -- both fail the same dependency check.
    """
    admin_token = await _admin_token(client, db_session)
    inv_data = await register_user(client)
    target_id = inv_data["user"]["id"]

    non_staff_data = await register_user(client)
    non_staff_token = non_staff_data["session_token"]

    resp = await client.patch(
        f"/api/v1/staff/users/{target_id}/unblock",
        headers=auth_headers(non_staff_token),
    )
    assert resp.status_code == 403


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
    assert "frozen_payments_count" in body
    assert body["total_users"] >= 1


@pytest.mark.asyncio
async def test_dashboard_stats_frozen_payments_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dashboard stats frozen_payments_count -> moves by exactly 1 when a
    single FROZEN payment is seeded.

    Shared-DB discipline: the dev DB accumulates payment rows across test
    runs, so we never assert an absolute count. Instead we read the count
    before seeding, add one FROZEN payment of our own (unique tx_hash via
    uuid4), and assert the count increased by exactly 1 -- robust against
    whatever pre-existing rows are already there.
    """
    admin_token = await _admin_token(client, db_session)
    inv_data = await register_user(client)
    user_id = UUID(inv_data["user"]["id"])

    resp_before = await client.get(
        "/api/v1/staff/dashboard/stats",
        headers=auth_headers(admin_token),
    )
    assert resp_before.status_code == 200
    count_before = resp_before.json()["frozen_payments_count"]

    payment = Payment(
        user_id=user_id,
        amount_cents=10000,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider="crypto_usdt_trc20",
        status=PaymentStatus.FROZEN,
        frozen_until=None,
        provider_data={"tx_hash": f"0x_test_{uuid4().hex[:8]}"},
    )
    db_session.add(payment)
    await db_session.commit()

    resp_after = await client.get(
        "/api/v1/staff/dashboard/stats",
        headers=auth_headers(admin_token),
    )
    assert resp_after.status_code == 200
    count_after = resp_after.json()["frozen_payments_count"]

    assert count_after == count_before + 1


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
        client
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
        client
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
        client
    )
    inv_token = inv_data["session_token"]
    submit_resp = await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(inv_token)
    )
    application_id = submit_resp.json()["id"]

    # Reject.
    resp = await client.post(
        f"/api/v1/staff/kyc/{application_id}/reject",
        json={},
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


# ---------------------------------------------------------------------------
# iter 2.6c B1: GET /staff/users?kyc_status= filter
# ---------------------------------------------------------------------------
#
# Robustness contract for this section:
#   * The dev DB is shared and can hold any number of pre-existing
#     users in any kyc_status. We never assert "all returned items
#     have kyc_status=X" -- pre-existing rows would fail that
#     tautology test on the day someone tests a different code path.
#   * Instead, each test creates a fresh investor in a known
#     kyc_status and runs two probes:
#       positive  -- ?kyc_status=<expected> includes our user
#       negative  -- ?kyc_status=<other>    excludes our user
#     The pair only passes when the WHERE clause is actually wired,
#     and tolerates arbitrary pollution from prior test runs.
#   * To survive heavily polluted dev DBs (>100 rows per status), we
#     find the user by id within the page; the service orders by
#     created_at DESC, so a just-registered investor lands on page 1
#     of a per_page=100 list with overwhelming probability. If a
#     future test fixture starts seeding >100 users per status, the
#     positive probe will need cursor pagination -- documented but
#     not implemented here.


async def _bring_investor_to_status(
    client: AsyncClient,
    admin_token: str,
    target_status: str,
) -> str:
    """Register an investor and walk them to the requested kyc_status.

    Returns the investor's user_id. `target_status` must be one of
    the four KYCStatus enum values: not_started, submitted, approved,
    rejected. Fails the test on any other value.

    We use the live KYC flow (POST /kyc/submit + POST /staff/kyc/.../
    approve|reject) instead of mutating User.kyc_status directly so
    the denormalised cache on User stays in sync with the
    KYCApplication row -- exactly as a real staff session would
    leave it.
    """
    inv_data = await register_user(client)
    user_id = inv_data["user"]["id"]
    inv_token = inv_data["session_token"]

    if target_status == "not_started":
        return user_id

    # All non-not_started states begin with a submit.
    submit_resp = await client.post(
        "/api/v1/kyc/submit", headers=auth_headers(inv_token)
    )
    assert submit_resp.status_code == 201, submit_resp.text
    application_id = submit_resp.json()["id"]

    if target_status == "submitted":
        return user_id

    if target_status == "approved":
        resp = await client.post(
            f"/api/v1/staff/kyc/{application_id}/approve",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 204, resp.text
        return user_id

    if target_status == "rejected":
        resp = await client.post(
            f"/api/v1/staff/kyc/{application_id}/reject",
            json={},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 204, resp.text
        return user_id

    pytest.fail(f"Unsupported target_status: {target_status!r}")
    return ""  # unreachable, keep type-checker happy


async def _fetch_user_ids_page(
    client: AsyncClient,
    admin_token: str,
    *,
    kyc_status: str,
    role: str | None = None,
    per_page: int = 100,
) -> set[str]:
    """Hit GET /staff/users with the requested filters; return id set.

    Returns the ids on page 1. The service orders by created_at DESC,
    so a fresh investor created within the same test will be near
    the top.
    """
    qs = f"?kyc_status={kyc_status}&per_page={per_page}"
    if role is not None:
        qs += f"&role={role}"
    resp = await client.get(
        f"/api/v1/staff/users{qs}",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {item["id"] for item in body["items"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_status,other_status",
    [
        ("not_started", "approved"),
        ("submitted", "approved"),
        ("approved", "rejected"),
        ("rejected", "approved"),
    ],
)
async def test_list_users_filter_kyc_status(
    client: AsyncClient,
    db_session: AsyncSession,
    target_status: str,
    other_status: str,
) -> None:
    """?kyc_status=<value> includes the freshly-staged investor
    and ?kyc_status=<other> excludes them.

    Positive probe + negative probe is the only configuration that
    proves the WHERE clause is actually applied. Iterating over the
    response would either pass tautologically when the SQL works or
    fail noisily on pre-existing rows that share a status; neither
    helps diagnose a regression.

    The (target, other) pairs are chosen so that `other` is a status
    the just-created investor CANNOT also satisfy after the live KYC
    walk:
      not_started -> approved   (just registered, never submitted)
      submitted   -> approved   (submitted, not yet approved)
      approved    -> rejected   (terminal in webhook -> approved)
      rejected    -> approved   (terminal in webhook -> rejected)
    """
    admin_token = await _admin_token(client, db_session)
    user_id = await _bring_investor_to_status(
        client, admin_token, target_status
    )

    # Positive probe: user must appear when filtering by their own status.
    matching_ids = await _fetch_user_ids_page(
        client, admin_token, kyc_status=target_status
    )
    assert user_id in matching_ids, (
        f"Investor {user_id} (kyc_status={target_status}) was not "
        f"surfaced by ?kyc_status={target_status}; got "
        f"{len(matching_ids)} ids on the first page"
    )

    # Negative probe: user must NOT appear when filtering by a status
    # they cannot currently hold.
    other_ids = await _fetch_user_ids_page(
        client, admin_token, kyc_status=other_status
    )
    assert user_id not in other_ids, (
        f"Investor {user_id} (actual kyc_status={target_status}) "
        f"leaked into ?kyc_status={other_status} page -- the WHERE "
        f"clause is not filtering"
    )


@pytest.mark.asyncio
async def test_list_users_filter_role_and_kyc_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?role=investor&kyc_status=approved -- both filters compose.

    Stage two investors:
      A: walks to approved.
      B: stays at not_started.
    Then probe with ?role=investor&kyc_status=approved:
      A must appear (positive)
      B must NOT appear (negative on kyc_status, role matches)
    This is the regression guard that proves the kyc_status clause is
    ANDed onto the existing role clause rather than replacing it. If
    the kyc_status filter were silently dropped when combined with
    role, B (a fresh not_started investor with role=investor) would
    leak into the response -- the negative assertion catches that.
    """
    admin_token = await _admin_token(client, db_session)
    approved_id = await _bring_investor_to_status(
        client, admin_token, "approved"
    )
    fresh_inv = await register_user(client)
    fresh_id = fresh_inv["user"]["id"]

    page_ids = await _fetch_user_ids_page(
        client,
        admin_token,
        kyc_status="approved",
        role="investor",
    )
    assert approved_id in page_ids, (
        f"Approved investor {approved_id} not in "
        f"?role=investor&kyc_status=approved page"
    )
    assert fresh_id not in page_ids, (
        f"Not-started investor {fresh_id} leaked into "
        f"?role=investor&kyc_status=approved page -- filters not "
        f"composing"
    )


@pytest.mark.asyncio
async def test_list_users_filter_kyc_status_invalid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """?kyc_status=<garbage> -> 422 from the FastAPI enum bind.

    Confirms the typed param rejects unknown values at the framework
    boundary before reaching the service layer.
    """
    admin_token = await _admin_token(client, db_session)

    resp = await client.get(
        "/api/v1/staff/users?kyc_status=garbage",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422, resp.text
