# =============================================================================
# CBSHOME Backend -- Leaderboard & Volume Tests (Sprint 7.3)
# =============================================================================
#
# Tests cover:
#   1:  VolumeProcessor.distribute_pool -- correct proportional distribution
#   2:  VolumeProcessor.distribute_pool -- empty agents -> empty result
#   3:  VolumeProcessor.distribute_pool -- SUM=0 invariant per transaction
#   4:  run_leaderboard_update -- aggregates volumes, writes snapshot
#   5:  run_monthly_payout -- distributes pool, writes VolumePayout + PassiveLedger
#   6:  GET /agent/leaderboard -- returns ranked agents, 200
#   7:  GET /agent/commissions/me -- returns commissions + volume bonuses
#   8:  GET /agent/leaderboard -- investor gets 403
#
# Email prefix: "s73_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import date, datetime, UTC
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commissions.constants import PeriodType
from app.modules.commissions.models import LeaderboardSnapshot, VolumePayout
from app.modules.ledgers.models import LedgerStatus, PassiveLedger
from app.modules.ledgers.service import record_passive_ledger
from app.modules.processors.volume import AgentRank, VolumeProcessor
from app.modules.purchases.constants import PurchaseLegalBasis
from app.modules.purchases.models import Purchase
from app.modules.referrals.models import ReferralAttribution, ReferralLink
from app.modules.users.models import User, UserRole
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    login_user,
    register_user,
)

EMAIL_PREFIX = "s73_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users before and after each test."""
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _create_user(
    client: AsyncClient, suffix: str
) -> tuple[UUID, str]:
    """Helper: register user, return (user_id, token)."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return UUID(data["user"]["id"]), data["session_token"]


async def _promote_to_agent(
    db_session: AsyncSession, user_id: UUID
) -> None:
    """Promote a user to agent role directly in DB."""
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.role = UserRole.AGENT
    await db_session.flush()


async def _get_platform_user_id(db_session: AsyncSession) -> UUID:
    """Get platform user ID."""
    stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    result = await db_session.execute(stmt)
    return result.scalar_one()


# ---------------------------------------------------------------------------
# 1: VolumeProcessor -- correct proportional distribution
# ---------------------------------------------------------------------------


def test_volume_processor_proportional_distribution() -> None:
    """VolumeProcessor distributes pool proportionally by volume."""
    platform_id = uuid4()
    agents = [
        AgentRank(agent_id=uuid4(), rank=1, volume_cents=60_000),
        AgentRank(agent_id=uuid4(), rank=2, volume_cents=40_000),
    ]

    processor = VolumeProcessor()
    transactions = processor.distribute_pool(
        agents_ranked=agents,
        pool_cents=10_000,
        platform_user_id=platform_id,
        period_type="monthly",
    )

    assert len(transactions) == 2

    # Agent 1: 60% of 10_000 = 6_000.
    assert transactions[0].entries[1].amount_cents == 6_000
    assert transactions[0].entries[1].user_id == agents[0].agent_id

    # Agent 2: 40% of 10_000 = 4_000.
    assert transactions[1].entries[1].amount_cents == 4_000
    assert transactions[1].entries[1].user_id == agents[1].agent_id


# ---------------------------------------------------------------------------
# 2: VolumeProcessor -- empty agents -> empty result
# ---------------------------------------------------------------------------


def test_volume_processor_empty_agents() -> None:
    """VolumeProcessor with no agents returns empty list."""
    processor = VolumeProcessor()
    transactions = processor.distribute_pool(
        agents_ranked=[],
        pool_cents=10_000,
        platform_user_id=uuid4(),
        period_type="monthly",
    )
    assert transactions == []


# ---------------------------------------------------------------------------
# 3: VolumeProcessor -- SUM=0 invariant
# ---------------------------------------------------------------------------


def test_volume_processor_sum_zero_invariant() -> None:
    """Every transaction produced by VolumeProcessor has SUM(entries)=0."""
    platform_id = uuid4()
    agents = [
        AgentRank(agent_id=uuid4(), rank=1, volume_cents=50_000),
        AgentRank(agent_id=uuid4(), rank=2, volume_cents=30_000),
        AgentRank(agent_id=uuid4(), rank=3, volume_cents=20_000),
    ]

    processor = VolumeProcessor()
    transactions = processor.distribute_pool(
        agents_ranked=agents,
        pool_cents=7_777,
        platform_user_id=platform_id,
        period_type="quarterly",
    )

    assert len(transactions) == 3
    for txn in transactions:
        entry_sum = sum(e.amount_cents for e in txn.entries)
        assert entry_sum == 0, (
            f"SUM(entries) = {entry_sum} != 0 for {txn.reason}"
        )


# ---------------------------------------------------------------------------
# 4: run_leaderboard_update -- writes snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard_update_writes_snapshot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """run_leaderboard_update aggregates volumes and writes snapshots."""
    agent_id, _ = await _create_user(client, "agent1")
    await _promote_to_agent(db_session, agent_id)
    inv_id, _ = await _create_user(client, "inv1")

    # Create referral link for agent.
    link = ReferralLink(agent_id=agent_id, code="LB_TEST1")
    db_session.add(link)
    await db_session.flush()

    # Create a purchase attributed to agent's link.
    purchase = Purchase(
        investor_id=inv_id,
        product_id=uuid4(),
        company_id=uuid4(),
        legal_basis=PurchaseLegalBasis.SALE,
        units=100,
        paid_cents=50_000,
        price_per_unit_cents=500,
        status="active",
    )
    db_session.add(purchase)
    await db_session.flush()

    attribution = ReferralAttribution(
        purchase_id=purchase.id,
        referral_link_id=link.id,
    )
    db_session.add(attribution)
    await db_session.commit()

    # Run leaderboard update.
    from app.modules.commissions.worker import run_leaderboard_update
    await run_leaderboard_update()

    # Verify snapshot was written.
    db_session.expire_all()
    stmt = (
        select(LeaderboardSnapshot)
        .where(LeaderboardSnapshot.agent_id == agent_id)
    )
    result = await db_session.execute(stmt)
    snapshots = list(result.scalars().all())

    assert len(snapshots) >= 1
    snap = snapshots[0]
    assert snap.rank == 1
    assert snap.volume_cents == 50_000
    assert snap.is_final is False


# ---------------------------------------------------------------------------
# 5: run_monthly_payout -- distributes pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monthly_payout_distributes_pool(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """run_monthly_payout distributes bonus pool to top agents."""
    agent_id, _ = await _create_user(client, "agent_pay")
    await _promote_to_agent(db_session, agent_id)
    inv_id, _ = await _create_user(client, "inv_pay")

    platform_id = await _get_platform_user_id(db_session)

    # Create referral link.
    link = ReferralLink(agent_id=agent_id, code="PAY_TST1")
    db_session.add(link)
    await db_session.flush()

    # Create purchase in PREVIOUS month so payout triggers.
    now = datetime.now(UTC)
    if now.month == 1:
        prev_month_dt = datetime(now.year - 1, 12, 15, tzinfo=UTC)
    else:
        prev_month_dt = datetime(now.year, now.month - 1, 15, tzinfo=UTC)

    purchase = Purchase(
        investor_id=inv_id,
        product_id=uuid4(),
        company_id=uuid4(),
        legal_basis=PurchaseLegalBasis.SALE,
        units=100,
        paid_cents=100_000,
        price_per_unit_cents=1000,
        status="active",
    )
    db_session.add(purchase)
    await db_session.flush()

    # Override created_at to previous month.
    from sqlalchemy import update as sa_update
    await db_session.execute(
        sa_update(Purchase)
        .where(Purchase.id == purchase.id)
        .values(created_at=prev_month_dt)
    )

    attribution = ReferralAttribution(
        purchase_id=purchase.id,
        referral_link_id=link.id,
    )
    db_session.add(attribution)

    # Ensure platform has enough passive balance for payout.
    await record_passive_ledger(
        db_session,
        user_id=platform_id,
        amount_cents=1_000_000,
        status=LedgerStatus.CONFIRMED,
        reason="test:platform_seed",
    )

    await db_session.commit()

    # Run monthly payout.
    from app.modules.commissions.worker import run_monthly_payout
    await run_monthly_payout()

    # Verify VolumePayout was created.
    db_session.expire_all()
    stmt = (
        select(VolumePayout)
        .where(VolumePayout.agent_id == agent_id)
    )
    result = await db_session.execute(stmt)
    payouts = list(result.scalars().all())

    assert len(payouts) == 1
    payout = payouts[0]
    assert payout.rank == 1
    assert payout.volume_cents == 100_000
    # Pool = 100_000 * 2% = 2_000. Agent gets 100% (only agent).
    assert payout.amount_cents == 2_000
    assert payout.pool_total_cents == 2_000

    # Verify PassiveLedger entry for agent.
    pl_stmt = (
        select(PassiveLedger)
        .where(
            PassiveLedger.user_id == agent_id,
            PassiveLedger.reason.startswith("volume_bonus:"),
        )
    )
    pl_result = await db_session.execute(pl_stmt)
    pl_entries = list(pl_result.scalars().all())
    assert len(pl_entries) == 1
    assert pl_entries[0].amount_cents == 2_000


# ---------------------------------------------------------------------------
# 6: GET /agent/leaderboard -- 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard_endpoint_returns_200(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /agent/leaderboard returns 200 with leaderboard data."""
    agent_id, _ = await _create_user(client, "agent_lb")
    await _promote_to_agent(db_session, agent_id)

    # Re-login after role change.
    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}agent_lb@example.com"
    )
    agent_token = login_data["session_token"]

    # Insert a snapshot directly.
    now = datetime.now(UTC)
    snapshot = LeaderboardSnapshot(
        agent_id=agent_id,
        rank=1,
        volume_cents=99_000,
        period_type=PeriodType.MONTHLY,
        period_start=date(now.year, now.month, 1),
        snapshot_at=now,
        is_final=False,
    )
    db_session.add(snapshot)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/agent/leaderboard",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["rank"] == 1
    assert body["entries"][0]["volume_cents"] == 99_000
    assert body["entries"][0]["is_me"] is True


# ---------------------------------------------------------------------------
# 7: GET /agent/commissions/me -- returns commissions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commissions_me_returns_entries(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /agent/commissions/me returns commission entries."""
    agent_id, _ = await _create_user(client, "agent_cm")
    await _promote_to_agent(db_session, agent_id)

    login_data = await login_user(
        client, email=f"{EMAIL_PREFIX}agent_cm@example.com"
    )
    agent_token = login_data["session_token"]

    # Insert a commission entry in passive_ledger.
    await record_passive_ledger(
        db_session,
        user_id=agent_id,
        amount_cents=5_000,
        status=LedgerStatus.CONFIRMED,
        reason=f"commission:l1:{uuid4()}:{uuid4()}",
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/agent/commissions/me",
        headers=auth_headers(agent_token),
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["type"] == "commission"
    assert body["items"][0]["amount_cents"] == 5_000
    assert body["items"][0]["level"] == 1


# ---------------------------------------------------------------------------
# 8: GET /agent/leaderboard -- investor gets 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard_investor_gets_403(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /agent/leaderboard returns 403 for investor."""
    _, inv_token = await _create_user(client, "inv_403")

    resp = await client.get(
        "/api/v1/agent/leaderboard",
        headers=auth_headers(inv_token),
    )
    assert resp.status_code == 403
