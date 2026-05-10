# =============================================================================
# CBSHOME Backend -- Commission Service (Sprint 7.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   get_leaderboard()      -- current leaderboard snapshot for display
#   get_my_commissions()   -- agent's commission + volume bonus history
#
# DATA SOURCES:
#   Leaderboard: LeaderboardSnapshot table (pre-computed by worker).
#   Commissions: PassiveLedger entries with reason prefix "commission:"
#                or "volume_bonus:". Enriched via JOINs for display.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

import re
from datetime import date, datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.commissions.constants import PeriodType, current_month_start
from app.modules.commissions.models import LeaderboardSnapshot, VolumePayout
from app.modules.commissions.schemas import (
    CommissionEntry,
    CommissionListResponse,
    LeaderboardEntry,
    LeaderboardResponse,
)
from app.modules.ledgers.models import PassiveLedger
from app.modules.purchases.models import Purchase
from app.modules.products.models import Product
from app.modules.users.models import User

logger = structlog.get_logger()

# Regex to parse commission reason: "commission:l{level}:{agent_id}:{purchase_id}"
_COMMISSION_RE = re.compile(
    r"^commission:l(\d+):([0-9a-f-]+):([0-9a-f-]+)$"
)

# Regex to parse volume bonus reason: "volume_bonus:{type}:{payout_id}"
_VOLUME_BONUS_RE = re.compile(
    r"^volume_bonus:(monthly|quarterly):([0-9a-f-]+)$"
)


def _extract_name(user: User) -> str:
    """Extract display name from User.profile JSONB."""
    if user.profile:
        first = user.profile.get("first_name", "")
        last = user.profile.get("last_name", "")
        name = f"{first} {last}".strip()
        if name:
            return name
    return "Agent"


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


async def get_leaderboard(
    current_agent_id: UUID,
    session: AsyncSession,
    period_type: str = PeriodType.MONTHLY,
) -> LeaderboardResponse:
    """Get current leaderboard for display.

    Returns ranked agents with names. Highlights current agent.
    Falls back to empty list if no snapshot exists yet.
    """
    period_start = current_month_start()

    # Load snapshot entries with agent users.
    stmt = (
        select(LeaderboardSnapshot, User)
        .join(User, LeaderboardSnapshot.agent_id == User.id)
        .where(
            LeaderboardSnapshot.period_type == period_type,
            LeaderboardSnapshot.period_start == period_start,
        )
        .order_by(LeaderboardSnapshot.rank)
        .limit(settings.leaderboard_top_monthly)
    )
    result = await session.execute(stmt)
    rows = result.all()

    entries: list[LeaderboardEntry] = []
    snapshot_at: datetime | None = None

    for snapshot, user in rows:
        if snapshot_at is None:
            snapshot_at = snapshot.snapshot_at

        entries.append(LeaderboardEntry(
            agent_id=snapshot.agent_id,
            agent_name=_extract_name(user),
            rank=snapshot.rank,
            volume_cents=snapshot.volume_cents,
            is_me=(snapshot.agent_id == current_agent_id),
        ))

    return LeaderboardResponse(
        entries=entries,
        snapshot_at=snapshot_at,
        period_start=period_start,
    )


# ---------------------------------------------------------------------------
# Commissions
# ---------------------------------------------------------------------------


async def get_my_commissions(
    agent_id: UUID,
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> CommissionListResponse:
    """Get agent's commission and volume bonus history.

    Reads from PassiveLedger by reason prefix, enriches with
    purchase/product/investor data via JOINs.
    """
    # -- Count total --
    count_stmt = (
        select(func.count())
        .select_from(PassiveLedger)
        .where(
            PassiveLedger.user_id == agent_id,
            PassiveLedger.amount_cents > 0,
            (
                PassiveLedger.reason.startswith("commission:")
                | PassiveLedger.reason.startswith("volume_bonus:")
            ),
        )
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # -- Load entries --
    entries_stmt = (
        select(PassiveLedger)
        .where(
            PassiveLedger.user_id == agent_id,
            PassiveLedger.amount_cents > 0,
            (
                PassiveLedger.reason.startswith("commission:")
                | PassiveLedger.reason.startswith("volume_bonus:")
            ),
        )
        .order_by(desc(PassiveLedger.created_at))
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(entries_stmt)
    ledger_entries = list(result.scalars().all())

    # -- Batched preload (Round 4 fix: collapse N+1 into 2 queries) --
    # The enrichment loop below used to issue one Purchase+Product+User
    # SELECT per commission entry and one VolumePayout SELECT per bonus
    # entry, i.e. up to 2*limit round-trips. Collect every id first,
    # then load both lookup tables in two batched queries.
    purchase_ids: list[UUID] = []
    payout_ids: list[UUID] = []
    for entry in ledger_entries:
        reason = entry.reason or ""
        if (m := _COMMISSION_RE.match(reason)) is not None:
            try:
                purchase_ids.append(UUID(m.group(3)))
            except ValueError:
                pass
        elif (m := _VOLUME_BONUS_RE.match(reason)) is not None:
            try:
                payout_ids.append(UUID(m.group(2)))
            except ValueError:
                pass

    purchases_by_id: dict[UUID, tuple[Purchase, Product, User]] = {}
    if purchase_ids:
        purchase_stmt = (
            select(Purchase, Product, User)
            .join(Product, Purchase.product_id == Product.id)
            .join(User, Purchase.investor_id == User.id)
            .where(Purchase.id.in_(purchase_ids))
        )
        for row in (await session.execute(purchase_stmt)).all():
            purchase, product, investor = row
            purchases_by_id[purchase.id] = (purchase, product, investor)

    payouts_by_id: dict[UUID, VolumePayout] = {}
    if payout_ids:
        payout_stmt = select(VolumePayout).where(VolumePayout.id.in_(payout_ids))
        payouts_by_id = {
            p.id: p
            for p in (await session.execute(payout_stmt)).scalars().all()
        }

    # -- Enrich entries --
    items: list[CommissionEntry] = []

    for entry in ledger_entries:
        commission_match = _COMMISSION_RE.match(entry.reason)
        volume_match = _VOLUME_BONUS_RE.match(entry.reason)

        if commission_match:
            level = int(commission_match.group(1))
            purchase_id_str = commission_match.group(3)

            # Load purchase -> product + investor for display.
            investor_name: str | None = None
            product_name: str | None = None

            try:
                purchase_id = UUID(purchase_id_str)
                row = purchases_by_id.get(purchase_id)
                if row is not None:
                    _purchase, product, investor = row
                    investor_name = _extract_name(investor)
                    product_name = product.name
            except ValueError:
                # Invalid UUID in reason string -- skip enrichment.
                pass

            items.append(CommissionEntry(
                type="commission",
                amount_cents=entry.amount_cents,
                status=entry.status,
                created_at=entry.created_at,
                level=level,
                investor_name=investor_name,
                product_name=product_name,
            ))

        elif volume_match:
            bonus_period_type = volume_match.group(1)
            payout_id_str = volume_match.group(2)

            # Load VolumePayout for rank info.
            rank: int | None = None
            try:
                payout_id = UUID(payout_id_str)
                payout = payouts_by_id.get(payout_id)
                if payout:
                    rank = payout.rank
            except ValueError:
                pass

            items.append(CommissionEntry(
                type="volume_bonus",
                amount_cents=entry.amount_cents,
                status=entry.status,
                created_at=entry.created_at,
                period_type=bonus_period_type,
                rank=rank,
            ))

        else:
            # Unknown reason format -- include as generic commission.
            items.append(CommissionEntry(
                type="commission",
                amount_cents=entry.amount_cents,
                status=entry.status,
                created_at=entry.created_at,
            ))

    return CommissionListResponse(items=items, total=total)
