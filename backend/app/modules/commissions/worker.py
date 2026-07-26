# =============================================================================
# AIVIS.ONE Backend -- Leaderboard & Volume Worker (Sprint 7.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   run_leaderboard_update()  -- refresh leaderboard snapshots (every 60 min)
#   run_monthly_payout()      -- distribute monthly bonus pool (once per month)
#   run_quarterly_payout()    -- distribute quarterly bonus pool (once per quarter)
#
# Called by asyncio.Task in main.py lifespan. Each function uses its own
# session -- failure in one does not block others.
#
# LEADERBOARD UPDATE:
#   1. Aggregate volumes: SUM(paid_cents) from Purchase via ReferralAttribution
#      for current month, excluding gift purchases.
#   2. DELETE existing non-final snapshots for current period.
#   3. INSERT new ranked snapshots.
#
# PAYOUT:
#   1. Check if payout already exists for previous period (idempotency).
#   2. Compute pool: SUM(paid_cents) all purchases in period * percent.
#   3. Read latest snapshot, take top-N.
#   4. Mark snapshot as final.
#   5. Call VolumeProcessor.distribute_pool() for pure calculation.
#   6. Write VolumePayout + PassiveLedger entries.
#
# SESSION MANAGEMENT:
#   Each operation uses get_session_factory() -- same pattern as
#   confirmation_worker and installment_worker.
# =============================================================================

import hashlib
from datetime import date, datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.constants import LedgerReason
from app.core.database import get_session_factory
from app.modules.commissions.constants import PeriodType, current_month_start
from app.modules.commissions.models import LeaderboardSnapshot, VolumePayout
from app.modules.ledgers.models import LedgerStatus, PassiveLedger
from app.modules.ledgers.service import record_passive_ledger
from app.modules.processors.volume import AgentRank, VolumeProcessor
from app.modules.purchases.models import Purchase
from app.modules.purchases.constants import PurchaseLegalBasis
from app.modules.referrals.models import ReferralAttribution, ReferralLink
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

_volume_processor = VolumeProcessor()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _period_lock_key(scope: str, period_type: str, period_start: date) -> int:
    """Deterministic 63-bit advisory-lock key for a period (R51).

    Replaces hash((period_type, str(period_start))): Python's hash()
    is randomized per process (PYTHONHASHSEED), so two workers in
    different processes derived DIFFERENT keys and the lock never
    serialized them -- under the broken lock the idempotency check in
    _distribute_pool could pass in both processes and the pool would
    be paid out twice. sha256 of a stable string is identical across
    processes and restarts.

    scope namespaces the key so the payout lock and the snapshot
    refresh lock never collide ("volume_payout" / "leaderboard_refresh").
    Each caller takes its locks in a fixed order, and the two scopes
    never nest, so no deadlock is possible.
    """
    digest = hashlib.sha256(
        f"{scope}:{period_type}:{period_start.isoformat()}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _previous_month_start() -> date:
    """First day of previous month."""
    now = datetime.now(UTC)
    if now.month == 1:
        return date(now.year - 1, 12, 1)
    return date(now.year, now.month - 1, 1)


def _current_quarter_start() -> date:
    """First day of current quarter."""
    now = datetime.now(UTC)
    q_month = ((now.month - 1) // 3) * 3 + 1
    return date(now.year, q_month, 1)


def _previous_quarter_start() -> date:
    """First day of previous quarter."""
    current = _current_quarter_start()
    if current.month == 1:
        return date(current.year - 1, 10, 1)
    return date(current.year, current.month - 3, 1)


def _next_period_start(period_start: date, period_type: str) -> date:
    """First day of the period AFTER period_start."""
    if period_type == PeriodType.MONTHLY:
        if period_start.month == 12:
            return date(period_start.year + 1, 1, 1)
        return date(period_start.year, period_start.month + 1, 1)
    else:
        # Quarterly.
        if period_start.month == 10:
            return date(period_start.year + 1, 1, 1)
        return date(period_start.year, period_start.month + 3, 1)


async def _get_platform_user_id(session: AsyncSession) -> UUID:
    """Load Platform user ID."""
    stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise RuntimeError("Platform user not found")
    return row


async def _aggregate_agent_volumes(
    session: AsyncSession,
    period_start: date,
    period_end: date,
) -> list[AgentRank]:
    """Aggregate sales volume per agent for a given period.

    Volume = SUM(paid_cents) of purchases attributed to agent's referral
    links, excluding gift purchases. Only active agents included.

    Returns list sorted by volume DESC with assigned ranks.
    """
    # Subquery: purchases in period with referral attribution to a link.
    stmt = (
        select(
            ReferralLink.agent_id,
            func.coalesce(func.sum(Purchase.paid_cents), 0).label("volume"),
        )
        .select_from(Purchase)
        .join(
            ReferralAttribution,
            ReferralAttribution.purchase_id == Purchase.id,
        )
        .join(
            ReferralLink,
            ReferralAttribution.referral_link_id == ReferralLink.id,
        )
        .join(
            User,
            ReferralLink.agent_id == User.id,
        )
        .where(
            Purchase.created_at >= period_start,
            Purchase.created_at < period_end,
            Purchase.legal_basis != PurchaseLegalBasis.GIFT,
            Purchase.status == "active",
            User.role == UserRole.AGENT,
            User.is_active.is_(True),
            ReferralAttribution.referral_link_id.is_not(None),
        )
        .group_by(ReferralLink.agent_id)
        .order_by(func.sum(Purchase.paid_cents).desc(), ReferralLink.agent_id)
    )

    result = await session.execute(stmt)
    rows = result.all()

    agents: list[AgentRank] = []
    for rank_idx, row in enumerate(rows, start=1):
        volume = int(row.volume)
        if volume <= 0:
            continue
        agents.append(AgentRank(
            agent_id=row.agent_id,
            rank=rank_idx,
            volume_cents=volume,
        ))

    return agents


async def _get_total_purchases_cents(
    session: AsyncSession,
    period_start: date,
    period_end: date,
) -> int:
    """SUM(paid_cents) for all purchases in period (excluding gifts)."""
    stmt = (
        select(func.coalesce(func.sum(Purchase.paid_cents), 0))
        .where(
            Purchase.created_at >= period_start,
            Purchase.created_at < period_end,
            Purchase.legal_basis != PurchaseLegalBasis.GIFT,
            Purchase.status == "active",
        )
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# Leaderboard update (every 60 min)
# ---------------------------------------------------------------------------


async def run_leaderboard_update() -> None:
    """Refresh leaderboard snapshots for current month and quarter.

    Deletes non-final snapshots and inserts fresh ones.
    """
    factory = get_session_factory()

    async with factory() as session:
        try:
            now = datetime.now(UTC)

            # -- Advisory locks (R51): serialize concurrent refreshers.
            # The replace cycle is DELETE non-final + INSERT; two
            # unserialized refreshers race that into duplicate rows --
            # and, after migration 0037 (uq_leaderboard_period_agent),
            # into IntegrityError. Both locks are taken up front in a
            # fixed order (monthly, then quarterly) by every refresher,
            # so refreshers cannot deadlock each other; the payout path
            # uses a different scope and holds only one lock.
            m_start = current_month_start()
            q_start_for_lock = _current_quarter_start()
            for scope_pt, scope_ps in (
                (PeriodType.MONTHLY, m_start),
                (PeriodType.QUARTERLY, q_start_for_lock),
            ):
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": _period_lock_key(
                        "leaderboard_refresh", scope_pt, scope_ps
                    )},
                )

            # -- Monthly snapshot --
            m_end = _next_period_start(m_start, PeriodType.MONTHLY)

            agents_monthly = await _aggregate_agent_volumes(
                session, m_start, m_end,
            )

            await session.execute(
                delete(LeaderboardSnapshot).where(
                    LeaderboardSnapshot.period_type == PeriodType.MONTHLY,
                    LeaderboardSnapshot.period_start == m_start,
                    LeaderboardSnapshot.is_final.is_(False),
                )
            )

            for agent in agents_monthly:
                session.add(LeaderboardSnapshot(
                    agent_id=agent.agent_id,
                    rank=agent.rank,
                    volume_cents=agent.volume_cents,
                    period_type=PeriodType.MONTHLY,
                    period_start=m_start,
                    snapshot_at=now,
                    is_final=False,
                ))

            # -- Quarterly snapshot --
            q_start = _current_quarter_start()
            q_end = _next_period_start(q_start, PeriodType.QUARTERLY)

            agents_quarterly = await _aggregate_agent_volumes(
                session, q_start, q_end,
            )

            await session.execute(
                delete(LeaderboardSnapshot).where(
                    LeaderboardSnapshot.period_type == PeriodType.QUARTERLY,
                    LeaderboardSnapshot.period_start == q_start,
                    LeaderboardSnapshot.is_final.is_(False),
                )
            )

            for agent in agents_quarterly:
                session.add(LeaderboardSnapshot(
                    agent_id=agent.agent_id,
                    rank=agent.rank,
                    volume_cents=agent.volume_cents,
                    period_type=PeriodType.QUARTERLY,
                    period_start=q_start,
                    snapshot_at=now,
                    is_final=False,
                ))

            await session.commit()

            logger.info(
                "leaderboard_updated",
                monthly_start=m_start.isoformat(),
                monthly_count=len(agents_monthly),
                quarterly_start=q_start.isoformat(),
                quarterly_count=len(agents_quarterly),
            )

        except Exception:
            await session.rollback()
            logger.exception("leaderboard_update_error")
            raise


# ---------------------------------------------------------------------------
# Monthly payout
# ---------------------------------------------------------------------------


async def run_monthly_payout() -> None:
    """Distribute monthly volume bonus pool if due.

    Triggers once when current month != previous snapshot month.
    Idempotent: skips if VolumePayout already exists for the period.
    """
    previous_start = _previous_month_start()
    current_start = current_month_start()

    # Only trigger if we've crossed into a new month.
    if current_start == previous_start:
        return

    factory = get_session_factory()

    async with factory() as session:
        try:
            await _distribute_pool(
                session=session,
                period_type=PeriodType.MONTHLY,
                period_start=previous_start,
                period_end=current_start,
                bonus_bp=settings.volume_bonus_monthly_bp,
                top_n=settings.leaderboard_top_monthly,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("monthly_payout_error")
            raise


# ---------------------------------------------------------------------------
# Quarterly payout
# ---------------------------------------------------------------------------


async def run_quarterly_payout() -> None:
    """Distribute quarterly volume bonus pool if due.

    Triggers once when current quarter != previous quarter.
    Idempotent: skips if VolumePayout already exists for the period.
    """
    previous_start = _previous_quarter_start()
    current_start = _current_quarter_start()

    # Only trigger if we've crossed into a new quarter.
    if current_start == previous_start:
        return

    factory = get_session_factory()

    async with factory() as session:
        try:
            await _distribute_pool(
                session=session,
                period_type=PeriodType.QUARTERLY,
                period_start=previous_start,
                period_end=current_start,
                bonus_bp=settings.volume_bonus_quarterly_bp,
                top_n=settings.leaderboard_top_quarterly,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("quarterly_payout_error")
            raise


# ---------------------------------------------------------------------------
# Shared payout logic
# ---------------------------------------------------------------------------


async def _distribute_pool(
    session: AsyncSession,
    period_type: str,
    period_start: date,
    period_end: date,
    bonus_bp: int,
    top_n: int,
) -> None:
    """Distribute volume bonus pool for a closed period.

    Concurrency-safe via advisory lock. Idempotent via existing check.
    Reads agent ranking from LeaderboardSnapshot (not re-aggregated).

    Args:
        bonus_bp: Bonus percentage in basis points (200 = 2.00%).
    """
    # -- 0. Advisory lock -- serialize concurrent workers.
    # R51: deterministic key (see _period_lock_key). The previous
    # hash()-based key was per-process random and did not lock across
    # workers -- a double-payout hazard.
    lock_key = _period_lock_key("volume_payout", period_type, period_start)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": lock_key},
    )

    # -- 1. Idempotency check (safe under advisory lock) --
    existing_stmt = (
        select(func.count())
        .select_from(VolumePayout)
        .where(
            VolumePayout.period_type == period_type,
            VolumePayout.period_start == period_start,
        )
    )
    existing_count = (await session.execute(existing_stmt)).scalar_one()
    if existing_count > 0:
        logger.info(
            "volume_payout_already_exists",
            period_type=period_type,
            period_start=period_start.isoformat(),
        )
        return

    # -- 2. Compute pool --
    total_purchases = await _get_total_purchases_cents(
        session, period_start, period_end,
    )
    pool_cents = total_purchases * bonus_bp // 10_000

    if pool_cents <= 0:
        logger.info(
            "volume_payout_empty_pool",
            period_type=period_type,
            period_start=period_start.isoformat(),
            total_purchases=total_purchases,
        )
        return

    # -- 3. Read ranked agents from snapshot (not re-aggregated) --
    snapshot_stmt = (
        select(LeaderboardSnapshot)
        .where(
            LeaderboardSnapshot.period_type == period_type,
            LeaderboardSnapshot.period_start == period_start,
        )
        .order_by(LeaderboardSnapshot.rank)
        .limit(top_n)
    )
    snapshot_result = await session.execute(snapshot_stmt)
    snapshots = list(snapshot_result.scalars().all())

    if not snapshots:
        # No snapshots -- fall back to live aggregation.
        agents = await _aggregate_agent_volumes(session, period_start, period_end)
        top_agents = agents[:top_n]
    else:
        top_agents = [
            AgentRank(
                agent_id=s.agent_id,
                rank=s.rank,
                volume_cents=s.volume_cents,
            )
            for s in snapshots
        ]

    if not top_agents:
        logger.info(
            "volume_payout_no_agents",
            period_type=period_type,
            period_start=period_start.isoformat(),
        )
        return

    # -- 4. Mark snapshots as final --
    await session.execute(
        update(LeaderboardSnapshot)
        .where(
            LeaderboardSnapshot.period_type == period_type,
            LeaderboardSnapshot.period_start == period_start,
            LeaderboardSnapshot.is_final.is_(False),
        )
        .values(is_final=True)
    )

    # -- 5. Get platform user + balance check --
    platform_user_id = await _get_platform_user_id(session)

    from app.modules.ledgers.service import get_passive_balance
    platform_balance = await get_passive_balance(session, platform_user_id)
    available = platform_balance["confirmed"] + platform_balance["frozen"]
    if available < pool_cents:
        logger.warning(
            "volume_payout_insufficient_platform_balance",
            period_type=period_type,
            period_start=period_start.isoformat(),
            pool_cents=pool_cents,
            available=available,
        )
        return

    # -- 6. Calculate distribution (pure logic) --
    transactions = _volume_processor.distribute_pool(
        agents_ranked=top_agents,
        pool_cents=pool_cents,
        platform_user_id=platform_user_id,
        period_type=period_type,
    )

    # -- 7. Write VolumePayout + PassiveLedger --
    # Build agent lookup for mapping txn -> agent data.
    agent_map = {a.agent_id: a for a in top_agents}

    reason_template = (
        LedgerReason.VOLUME_BONUS_MONTHLY
        if period_type == PeriodType.MONTHLY
        else LedgerReason.VOLUME_BONUS_QUARTERLY
    )

    # Iterate transactions (not zip with top_agents -- H-1 fix).
    # Extract agent_id from credit entry (entries[1].user_id).
    for txn in transactions:
        agent_id = txn.entries[1].user_id  # Credit entry = agent.
        agent_data = agent_map[agent_id]

        # Create VolumePayout record.
        payout = VolumePayout(
            agent_id=agent_id,
            period_type=period_type,
            period_start=period_start,
            amount_cents=txn.entries[1].amount_cents,
            rank=agent_data.rank,
            volume_cents=agent_data.volume_cents,
            pool_total_cents=pool_cents,
        )
        session.add(payout)
        await session.flush()

        # Replace {payout_id} placeholder in reason.
        reason = reason_template.format(payout_id=str(payout.id))

        # Write ledger entries.
        for entry in txn.entries:
            await record_passive_ledger(
                session,
                user_id=entry.user_id,
                amount_cents=entry.amount_cents,
                status=LedgerStatus.CONFIRMED,
                reason=reason,
            )

    # -- 8. Audit --
    await record_audit(
        session=session,
        event=f"volume_bonus.{period_type}_distributed",
        actor_id=platform_user_id,
        actor_type="system",
        target_type="volume_payout",
        target_id=platform_user_id,
        data={
            "period_type": period_type,
            "period_start": period_start.isoformat(),
            "pool_total_cents": pool_cents,
            "agents_count": len(transactions),
            "total_purchases_cents": total_purchases,
        },
    )

    logger.info(
        "volume_payout_distributed",
        period_type=period_type,
        period_start=period_start.isoformat(),
        pool_cents=pool_cents,
        agents_count=len(transactions),
    )
