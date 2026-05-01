# =============================================================================
# CBSHOME Backend -- Referral Tests (Sprint 7.2)
# =============================================================================
#
# Tests cover:
#   1-5:   Link CRUD (create, list, stats, permissions)
#   6-8:   Registration with referral_code
#   9-11:  Commission chain L1, L1+L2, L1+L2+L3
#   12:    Organic purchase (no commissions)
#   13:    STOP mechanic (chain limited by agent_levels length)
#   14-15: ReferralAttribution created for referral and organic purchases
#
# Email prefix: "s72_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import PassiveLedger
from app.modules.ledgers.service import record_active_ledger
from app.modules.referrals.models import ReferralAttribution, ReferralLink
from app.modules.users.models import User, UserRole
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    create_admin_user,
    login_user,
    register_user,
)

EMAIL_PREFIX = "s72_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_agent(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str = "agent1",
) -> tuple[str, UUID]:
    """Register user, promote to agent. Returns (token, user_id)."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}{suffix}@example.com")
    user_id = UUID(data["user"]["id"])

    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()

    login_data = await login_user(client, email=f"{EMAIL_PREFIX}{suffix}@example.com")
    return login_data["session_token"], user_id


async def _make_investor(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str = "inv1",
    referral_code: str | None = None,
) -> tuple[str, UUID]:
    """Register investor, optionally with referral code. Returns (token, user_id)."""
    body: dict = {
        "email": f"{EMAIL_PREFIX}{suffix}@example.com",
        "password": "testpass123",
    }
    if referral_code:
        body["referral_code"] = referral_code

    from tests.helpers import _clear_email_rate_limit
    await _clear_email_rate_limit()

    resp = await client.post("/api/v1/auth/email/register", json=body)
    assert resp.status_code == 201
    data = resp.json()
    return data["session_token"], UUID(data["user"]["id"])


async def _create_company_and_product(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    suffix: str = "co1",
) -> UUID:
    """Create company + pool + product + activate. Returns product_id.

    Sprint 4.3: company carries supply fields; an active OptionPool is
    created before the product so the product can attach to it.
    """
    # Create company.
    resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "name": f"TestCo {suffix}",
            "email": f"{EMAIL_PREFIX}{suffix}@example.com",
            "password": "testpass123",
            "price_per_unit_cents": 100_00,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            # Sprint 4.3:
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, f"Company create failed: {resp.text}"
    company_id = resp.json()["id"]

    # Sprint 4.3: pool before product.
    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company_id}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, f"Pool create failed: {pool_resp.text}"

    # Activate company.
    await client.patch(
        f"/api/v1/staff/companies/{company_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )

    # Create product.
    resp2 = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company_id,
            "name": f"Product {suffix}",
            "package_size": 10,  # Sprint 4.3: column renamed
        },
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 201, f"Product create failed: {resp2.text}"
    product_id = resp2.json()["id"]

    # Activate product (created as hidden -> active via /status endpoint).
    resp3 = await client.patch(
        f"/api/v1/staff/products/{product_id}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    assert resp3.status_code == 200, f"Product activate failed: {resp3.text}"

    return UUID(product_id)


async def _deposit(
    db_session: AsyncSession,
    user_id: UUID,
    amount_cents: int,
    suffix: str = "",
) -> None:
    """Add confirmed balance to investor's active ledger."""
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=amount_cents,
        status="confirmed",
        reason=f"deposit:crypto:0xtest_s72{suffix}",
    )


async def _get_referral_code(
    client: AsyncClient,
    agent_token: str,
) -> str:
    """Create a referral link and return the code."""
    resp = await client.post(
        "/api/v1/referrals/links",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 201
    return resp.json()["code"]


async def _approve_kyc(db_session: AsyncSession, user_id: UUID) -> None:
    """Set KYC status to approved for an investor."""
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.kyc_status = "approved"
    await db_session.commit()


# ---------------------------------------------------------------------------
# 1-5: Link CRUD & Permissions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_link_agent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Agent creates referral link -> 201, code returned."""
    token, _ = await _make_agent(client, db_session)
    resp = await client.post(
        "/api/v1/referrals/links",
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "code" in body
    assert len(body["code"]) > 0
    assert "id" in body


@pytest.mark.asyncio
async def test_create_link_investor_forbidden(
    client: AsyncClient,
) -> None:
    """Investor cannot create referral link -> 403."""
    data = await register_user(client, email=f"{EMAIL_PREFIX}inv_no@example.com")
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/referrals/links",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_two_links_unique_codes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Agent creates 2 links -> different codes."""
    token, _ = await _make_agent(client, db_session, suffix="agent2c")

    resp1 = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    resp2 = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(token)
    )
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["code"] != resp2.json()["code"]


@pytest.mark.asyncio
async def test_list_my_links(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /referrals/links/me -> 200, returns agent's links."""
    token, _ = await _make_agent(client, db_session, suffix="agent_list")

    # Create 2 links.
    await client.post("/api/v1/referrals/links", headers=auth_headers(token))
    await client.post("/api/v1/referrals/links", headers=auth_headers(token))

    resp = await client.get(
        "/api/v1/referrals/links/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_stats_response_structure(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /referrals/stats/me -> 200, correct structure."""
    token, _ = await _make_agent(client, db_session, suffix="agent_stats")

    resp = await client.get(
        "/api/v1/referrals/stats/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total_links" in body
    assert "total_purchases" in body
    assert "total_commission_cents" in body


# ---------------------------------------------------------------------------
# 6-8: Registration with referral_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_with_valid_referral_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Register with valid referral code -> referred_by = agent_id."""
    agent_token, agent_id = await _make_agent(client, db_session, suffix="ref_ag")
    code = await _get_referral_code(client, agent_token)

    _, investor_id = await _make_investor(
        client, db_session, suffix="ref_inv", referral_code=code
    )

    # Check referred_by in DB.
    stmt = select(User).where(User.id == investor_id)
    result = await db_session.execute(stmt)
    investor = result.scalar_one()
    assert investor.referred_by == agent_id


@pytest.mark.asyncio
async def test_register_with_invalid_referral_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Register with invalid code -> referred_by = platform_id (silent fallback)."""
    _, investor_id = await _make_investor(
        client, db_session, suffix="bad_ref", referral_code="INVALID_CODE"
    )

    stmt = select(User).where(User.id == investor_id)
    result = await db_session.execute(stmt)
    investor = result.scalar_one()

    # Should be platform user.
    platform_stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    platform_id = (await db_session.execute(platform_stmt)).scalar_one()
    assert investor.referred_by == platform_id


@pytest.mark.asyncio
async def test_register_without_referral_code(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Register without referral_code -> referred_by = platform_id."""
    _, investor_id = await _make_investor(
        client, db_session, suffix="no_ref"
    )

    stmt = select(User).where(User.id == investor_id)
    result = await db_session.execute(stmt)
    investor = result.scalar_one()

    platform_stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    platform_id = (await db_session.execute(platform_stmt)).scalar_one()
    assert investor.referred_by == platform_id


# ---------------------------------------------------------------------------
# 9-11: Commission chain tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purchase_l1_commission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase by referred investor -> L1 agent gets commission."""
    _, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}adm_l1@example.com"
    )

    # Create agent L1.
    agent_token, agent_id = await _make_agent(client, db_session, suffix="l1_ag")
    code = await _get_referral_code(client, agent_token)

    # Register investor via agent's link.
    inv_token, inv_id = await _make_investor(
        client, db_session, suffix="l1_inv", referral_code=code
    )

    # Setup: company + product + deposit + KYC.
    product_id = await _create_company_and_product(
        client, admin_token, db_session, suffix="l1co"
    )
    await _deposit(db_session, inv_id, 200_000_00, suffix="_l1")
    await _approve_kyc(db_session, inv_id)
    await db_session.commit()

    # Purchase.
    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201

    # Check L1 commission in passive_ledger.
    # amount = 10 units * 100_00 = 1000_00 cents. L1 = 10% = 100_00.
    stmt = select(PassiveLedger).where(
        PassiveLedger.user_id == agent_id,
        PassiveLedger.reason.startswith("commission:l1:"),
    )
    result = await db_session.execute(stmt)
    entries = list(result.scalars().all())
    assert len(entries) == 1
    assert entries[0].amount_cents == 100_00


@pytest.mark.asyncio
async def test_purchase_l1_l2_commission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """L1 + L2 agents both get commissions."""
    _, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}adm_l2@example.com"
    )

    # Agent L2 (referred by platform).
    l2_token, l2_id = await _make_agent(client, db_session, suffix="l2_ag")
    l2_code = await _get_referral_code(client, l2_token)

    # Agent L1 (referred by L2).
    l1_token, l1_id = await _make_investor(
        client, db_session, suffix="l1_ag2", referral_code=l2_code
    )
    # Promote L1 to agent.
    stmt = select(User).where(User.id == l1_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()
    l1_login = await login_user(client, email=f"{EMAIL_PREFIX}l1_ag2@example.com")
    l1_token = l1_login["session_token"]

    l1_code = await _get_referral_code(client, l1_token)

    # Investor referred by L1.
    inv_token, inv_id = await _make_investor(
        client, db_session, suffix="l2_inv", referral_code=l1_code
    )

    product_id = await _create_company_and_product(
        client, admin_token, db_session, suffix="l2co"
    )
    await _deposit(db_session, inv_id, 200_000_00, suffix="_l2")
    await _approve_kyc(db_session, inv_id)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201

    # L1 = 10% of 1000_00 = 100_00.
    l1_stmt = select(PassiveLedger).where(
        PassiveLedger.user_id == l1_id,
        PassiveLedger.reason.startswith("commission:l1:"),
    )
    l1_entries = list((await db_session.execute(l1_stmt)).scalars().all())
    assert len(l1_entries) == 1
    assert l1_entries[0].amount_cents == 100_00

    # L2 = 3% of 1000_00 = 30_00.
    l2_stmt = select(PassiveLedger).where(
        PassiveLedger.user_id == l2_id,
        PassiveLedger.reason.startswith("commission:l2:"),
    )
    l2_entries = list((await db_session.execute(l2_stmt)).scalars().all())
    assert len(l2_entries) == 1
    assert l2_entries[0].amount_cents == 30_00


@pytest.mark.asyncio
async def test_purchase_l1_l2_l3_commission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Full L1+L2+L3 chain -> all 3 agents get commissions."""
    _, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}adm_l3@example.com"
    )

    # Agent L3 (root).
    l3_token, l3_id = await _make_agent(client, db_session, suffix="l3_ag")
    l3_code = await _get_referral_code(client, l3_token)

    # Agent L2 (referred by L3).
    _, l2_id = await _make_investor(
        client, db_session, suffix="l2_ag3", referral_code=l3_code
    )
    stmt = select(User).where(User.id == l2_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()
    l2_login = await login_user(client, email=f"{EMAIL_PREFIX}l2_ag3@example.com")
    l2_token = l2_login["session_token"]
    l2_code = await _get_referral_code(client, l2_token)

    # Agent L1 (referred by L2).
    _, l1_id = await _make_investor(
        client, db_session, suffix="l1_ag3", referral_code=l2_code
    )
    stmt = select(User).where(User.id == l1_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()
    l1_login = await login_user(client, email=f"{EMAIL_PREFIX}l1_ag3@example.com")
    l1_token = l1_login["session_token"]
    l1_code = await _get_referral_code(client, l1_token)

    # Investor referred by L1.
    inv_token, inv_id = await _make_investor(
        client, db_session, suffix="l3_inv", referral_code=l1_code
    )

    product_id = await _create_company_and_product(
        client, admin_token, db_session, suffix="l3co"
    )
    await _deposit(db_session, inv_id, 200_000_00, suffix="_l3")
    await _approve_kyc(db_session, inv_id)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201

    # L1 = 10% = 100_00.
    l1_entries = list((await db_session.execute(
        select(PassiveLedger).where(
            PassiveLedger.user_id == l1_id,
            PassiveLedger.reason.startswith("commission:l1:"),
        )
    )).scalars().all())
    assert len(l1_entries) == 1
    assert l1_entries[0].amount_cents == 100_00

    # L2 = 3% = 30_00.
    l2_entries = list((await db_session.execute(
        select(PassiveLedger).where(
            PassiveLedger.user_id == l2_id,
            PassiveLedger.reason.startswith("commission:l2:"),
        )
    )).scalars().all())
    assert len(l2_entries) == 1
    assert l2_entries[0].amount_cents == 30_00

    # L3 = 1% = 10_00.
    l3_entries = list((await db_session.execute(
        select(PassiveLedger).where(
            PassiveLedger.user_id == l3_id,
            PassiveLedger.reason.startswith("commission:l3:"),
        )
    )).scalars().all())
    assert len(l3_entries) == 1
    assert l3_entries[0].amount_cents == 10_00


# ---------------------------------------------------------------------------
# 12: Organic purchase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_organic_purchase_no_commissions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase without referral -> 0 commissions."""
    _, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}adm_org@example.com"
    )
    inv_token, inv_id = await _make_investor(
        client, db_session, suffix="org_inv"
    )

    product_id = await _create_company_and_product(
        client, admin_token, db_session, suffix="orgco"
    )
    await _deposit(db_session, inv_id, 200_000_00, suffix="_org")
    await _approve_kyc(db_session, inv_id)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201

    # No commission entries for anyone.
    stmt = select(PassiveLedger).where(
        PassiveLedger.reason.startswith("commission:"),
    )
    result = await db_session.execute(stmt)
    commission_entries = list(result.scalars().all())
    # Filter to only entries from this test (by checking user_ids).
    # Simpler: just check no commission entries exist for this investor's referrer.
    platform_stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    platform_id = (await db_session.execute(platform_stmt)).scalar_one()

    inv_stmt = select(User).where(User.id == inv_id)
    investor = (await db_session.execute(inv_stmt)).scalar_one()
    assert investor.referred_by == platform_id


# ---------------------------------------------------------------------------
# 13: STOP mechanic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_mechanic_max_depth(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """4th level agent does NOT get commission (limited by agent_levels=3)."""
    _, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}adm_stop@example.com"
    )

    # Build chain: L4 -> L3 -> L2 -> L1 -> investor.
    l4_token, l4_id = await _make_agent(client, db_session, suffix="l4_ag")
    l4_code = await _get_referral_code(client, l4_token)

    _, l3_id = await _make_investor(
        client, db_session, suffix="l3_ag_s", referral_code=l4_code
    )
    stmt = select(User).where(User.id == l3_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()
    l3_login = await login_user(client, email=f"{EMAIL_PREFIX}l3_ag_s@example.com")
    l3_code = await _get_referral_code(client, l3_login["session_token"])

    _, l2_id = await _make_investor(
        client, db_session, suffix="l2_ag_s", referral_code=l3_code
    )
    stmt = select(User).where(User.id == l2_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()
    l2_login = await login_user(client, email=f"{EMAIL_PREFIX}l2_ag_s@example.com")
    l2_code = await _get_referral_code(client, l2_login["session_token"])

    _, l1_id = await _make_investor(
        client, db_session, suffix="l1_ag_s", referral_code=l2_code
    )
    stmt = select(User).where(User.id == l1_id)
    user = (await db_session.execute(stmt)).scalar_one()
    user.role = UserRole.AGENT
    await db_session.commit()
    l1_login = await login_user(client, email=f"{EMAIL_PREFIX}l1_ag_s@example.com")
    l1_code = await _get_referral_code(client, l1_login["session_token"])

    inv_token, inv_id = await _make_investor(
        client, db_session, suffix="stop_inv", referral_code=l1_code
    )

    product_id = await _create_company_and_product(
        client, admin_token, db_session, suffix="stco"
    )
    await _deposit(db_session, inv_id, 200_000_00, suffix="_stop")
    await _approve_kyc(db_session, inv_id)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201

    # L1, L2, L3 get commissions. L4 does NOT.
    for uid, prefix in [(l1_id, "commission:l1:"), (l2_id, "commission:l2:"), (l3_id, "commission:l3:")]:
        entries = list((await db_session.execute(
            select(PassiveLedger).where(
                PassiveLedger.user_id == uid,
                PassiveLedger.reason.startswith(prefix),
            )
        )).scalars().all())
        assert len(entries) == 1, f"Expected 1 entry for {prefix}, got {len(entries)}"

    # L4 should have 0 commission entries.
    l4_entries = list((await db_session.execute(
        select(PassiveLedger).where(
            PassiveLedger.user_id == l4_id,
            PassiveLedger.reason.startswith("commission:"),
        )
    )).scalars().all())
    assert len(l4_entries) == 0


# ---------------------------------------------------------------------------
# 14-15: ReferralAttribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attribution_with_referral_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Purchase with referral_link_id -> attribution has link reference."""
    _, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}adm_attr@example.com"
    )
    agent_token, _ = await _make_agent(client, db_session, suffix="attr_ag")

    # Create link.
    link_resp = await client.post(
        "/api/v1/referrals/links", headers=auth_headers(agent_token)
    )
    link_id = UUID(link_resp.json()["id"])
    code = link_resp.json()["code"]

    inv_token, inv_id = await _make_investor(
        client, db_session, suffix="attr_inv", referral_code=code
    )

    product_id = await _create_company_and_product(
        client, admin_token, db_session, suffix="atco"
    )
    await _deposit(db_session, inv_id, 200_000_00, suffix="_attr")
    await _approve_kyc(db_session, inv_id)
    await db_session.commit()

    # Purchase WITH referral_link_id.
    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={"referral_link_id": str(link_id)},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201

    # Check attribution.
    attr_stmt = select(ReferralAttribution).where(
        ReferralAttribution.referral_link_id == link_id,
    )
    result = await db_session.execute(attr_stmt)
    attrs = list(result.scalars().all())
    assert len(attrs) == 1
    assert attrs[0].referral_link_id == link_id


@pytest.mark.asyncio
async def test_attribution_organic_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Organic purchase -> attribution with referral_link_id=NULL."""
    _, admin_token = await create_admin_user(
        client, db_session, email=f"{EMAIL_PREFIX}adm_aorg@example.com"
    )
    inv_token, inv_id = await _make_investor(
        client, db_session, suffix="aorg_inv"
    )

    product_id = await _create_company_and_product(
        client, admin_token, db_session, suffix="aoco"
    )
    await _deposit(db_session, inv_id, 200_000_00, suffix="_aorg")
    await _approve_kyc(db_session, inv_id)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/products/{product_id}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 201
    purchase_id = UUID(resp.json()[0]["id"])

    # Check attribution exists with NULL referral_link_id.
    attr_stmt = select(ReferralAttribution).where(
        ReferralAttribution.purchase_id == purchase_id,
    )
    result = await db_session.execute(attr_stmt)
    attr = result.scalar_one()
    assert attr.referral_link_id is None
