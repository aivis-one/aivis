# =============================================================================
# CBSHOME Backend -- Commission Models (Sprint 7.3)
# =============================================================================
#
# LeaderboardSnapshot:
#   Periodic snapshot of agent rankings by sales volume.
#   Updated every 60 minutes by leaderboard_worker for current period.
#   Frozen (is_final=True) when volume bonuses are distributed at
#   period end. Historical snapshots preserved for audit trail.
#
# VolumePayout:
#   Audit record of volume bonus distribution. One per agent per period.
#   Links to PassiveLedger via reason string (volume_bonus:{type}:{id}).
#   Stores rank + volume at payout time (no FK to snapshot -- simple
#   denormalization for query simplicity).
#
# RULES:
#   - Both tables are immutable after is_final=True / creation.
#   - VolumePayout has UNIQUE(agent_id, period_type, period_start) --
#     one bonus per agent per period.
#   - LeaderboardSnapshot rows for current period are replaced on each
#     worker cycle (DELETE + INSERT WHERE is_final=False).
# =============================================================================

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import UUIDMixin


class LeaderboardSnapshot(UUIDMixin, Base):
    """Periodic snapshot of agent ranking by sales volume."""

    __tablename__ = "leaderboard_snapshots"

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # SUM(paid_cents) of purchases attributed to this agent's chain.
    volume_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # "monthly" or "quarterly".
    period_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # First day of the period (e.g. 2026-04-01).
    period_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # When this snapshot was computed.
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # False = live (overwritten each cycle). True = frozen after payout.
    is_final: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Fast lookup for GET /agent/leaderboard.
        Index(
            "ix_leaderboard_period_rank",
            "period_type",
            "period_start",
            "rank",
        ),
        # Lookup by agent for history.
        Index(
            "ix_leaderboard_agent_period",
            "agent_id",
            "period_type",
            "period_start",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<LeaderboardSnapshot agent={self.agent_id} "
            f"rank={self.rank} volume={self.volume_cents} "
            f"period={self.period_type}:{self.period_start}>"
        )


class VolumePayout(UUIDMixin, Base):
    """Audit record of volume bonus payout to an agent."""

    __tablename__ = "volume_payouts"

    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # "monthly" or "quarterly".
    period_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # First day of the period.
    period_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # Bonus amount credited to agent's passive_ledger.
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Agent's rank at payout time (denormalized from snapshot).
    rank: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Agent's volume at payout time (denormalized from snapshot).
    volume_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Total pool distributed in this period.
    pool_total_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # One bonus per agent per period.
        UniqueConstraint(
            "agent_id",
            "period_type",
            "period_start",
            name="uq_volume_payouts_agent_period",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<VolumePayout agent={self.agent_id} "
            f"amount={self.amount_cents} rank={self.rank} "
            f"period={self.period_type}:{self.period_start}>"
        )
