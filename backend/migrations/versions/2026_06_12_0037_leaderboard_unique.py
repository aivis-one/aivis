"""leaderboard_snapshots unique per agent+period -- R51

Revision ID: 0037_leaderboard_unique
Revises: 0036_txn_type_purchase_rev
Create Date: 2026-06-12 00:00:00.000000

The snapshot refresh cycle (commissions/worker.py) is DELETE non-final
+ INSERT. Before R51 it ran with no serialization, so two concurrent
refreshers could duplicate (period_type, period_start, agent_id) rows;
the payout path reads snapshots LIMIT top_n, so a duplicated agent in
the top would be paid a double share. R51 adds an advisory lock to the
refresh; this migration adds the DB-level backstop.

UPGRADE runs in two steps:
  1. DEDUPE: among duplicates of (period_type, period_start, agent_id),
     keep the newest snapshot (max snapshot_at, id as tiebreaker) and
     delete the rest. Snapshots are derived data, recomputed hourly --
     deleting stale duplicates loses nothing.
  2. Create uq_leaderboard_period_agent.

DOWNGRADE drops the constraint only (deduped rows are not restored --
they were stale derived data).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_leaderboard_unique"
down_revision: Union[str, None] = "0036_txn_type_purchase_rev"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_snapshots = sa.table(
    "leaderboard_snapshots",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("period_type", sa.String),
    sa.column("period_start", sa.Date),
    sa.column("agent_id", postgresql.UUID(as_uuid=True)),
    sa.column("snapshot_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    # -- 1. Dedupe: keep the newest row per (period_type, period_start,
    # agent_id); ties broken by id so the survivor set is deterministic.
    s1 = _snapshots.alias("s1")
    s2 = _snapshots.alias("s2")

    # s1 is stale if a sibling s2 with the same key is newer
    # (or equally new with a greater id).
    newer_sibling_exists = (
        sa.select(sa.literal(1))
        .select_from(s2)
        .where(
            s2.c.period_type == s1.c.period_type,
            s2.c.period_start == s1.c.period_start,
            s2.c.agent_id == s1.c.agent_id,
            sa.or_(
                s2.c.snapshot_at > s1.c.snapshot_at,
                sa.and_(
                    s2.c.snapshot_at == s1.c.snapshot_at,
                    s2.c.id > s1.c.id,
                ),
            ),
        )
        .exists()
    )

    stale_ids = sa.select(s1.c.id).where(newer_sibling_exists)
    op.execute(sa.delete(_snapshots).where(_snapshots.c.id.in_(stale_ids)))

    # -- 2. Backstop constraint.
    op.create_unique_constraint(
        "uq_leaderboard_period_agent",
        "leaderboard_snapshots",
        ["period_type", "period_start", "agent_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_leaderboard_period_agent",
        "leaderboard_snapshots",
        type_="unique",
    )
