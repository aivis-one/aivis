"""commissions -- LeaderboardSnapshot + VolumePayout tables

Revision ID: 0016_commissions
Revises: 0015_referrals_td
Create Date: 2026-04-12 00:00:00.000000

Changes:
  - CREATE TABLE leaderboard_snapshots (agent rankings by volume)
  - CREATE TABLE volume_payouts (bonus distribution audit)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_commissions"
down_revision: Union[str, None] = "0015_referrals_td"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create commission tables."""

    # -- leaderboard_snapshots --
    op.create_table(
        "leaderboard_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("volume_cents", sa.BigInteger(), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "is_final",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_leaderboard_period_rank",
        "leaderboard_snapshots",
        ["period_type", "period_start", "rank"],
    )
    op.create_index(
        "ix_leaderboard_agent_period",
        "leaderboard_snapshots",
        ["agent_id", "period_type", "period_start"],
    )

    # -- volume_payouts --
    op.create_table(
        "volume_payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("volume_cents", sa.BigInteger(), nullable=False),
        sa.Column("pool_total_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_id",
            "period_type",
            "period_start",
            name="uq_volume_payouts_agent_period",
        ),
    )


def downgrade() -> None:
    """Drop commission tables."""
    op.drop_table("volume_payouts")
    op.drop_index("ix_leaderboard_agent_period", table_name="leaderboard_snapshots")
    op.drop_index("ix_leaderboard_period_rank", table_name="leaderboard_snapshots")
    op.drop_table("leaderboard_snapshots")
