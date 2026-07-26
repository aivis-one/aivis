# =============================================================================
# AIVIS.ONE Backend -- Volume Worker / Leaderboard Tests (R51)
# =============================================================================
#
# Tests cover:
#   1: _period_lock_key is deterministic -- pinned to a precomputed
#      constant so any regression back to hash() (randomized per
#      process by PYTHONHASHSEED, the pre-R51 double-payout hazard)
#      fails loudly; also pins the 63-bit range and scope separation
#   2: uq_leaderboard_period_agent (migration 0037) rejects a second
#      snapshot row for the same (period_type, period_start, agent_id)
#
# Shared dev DB note: test 2 builds its key from a freshly registered
# agent (unique UUID per run), so runs never collide on the constraint.
# =============================================================================

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commissions.constants import PeriodType
from app.modules.commissions.models import LeaderboardSnapshot
from app.modules.commissions.worker import _period_lock_key
from tests.helpers import register_user


def test_period_lock_key_is_deterministic() -> None:
    """R51: the advisory-lock key must be identical across processes.

    The pinned constant was computed once from the sha256 derivation;
    if the implementation regresses to anything process-dependent
    (e.g. hash(), randomized by PYTHONHASHSEED), this assert breaks in
    some runs -- which is exactly the loud failure we want, because a
    per-process key means the payout lock never serializes concurrent
    workers and the idempotency check can double-pay the pool.
    """
    key = _period_lock_key("volume_payout", "monthly", date(2026, 1, 1))
    assert key == 4986140235562368025

    # Stable on repeat call, positive, within signed-64-bit range
    # (pg_advisory_xact_lock takes bigint).
    assert _period_lock_key("volume_payout", "monthly", date(2026, 1, 1)) == key
    assert 0 <= key <= 0x7FFFFFFFFFFFFFFF

    # Scope namespacing: refresh and payout locks never collide.
    refresh_key = _period_lock_key(
        "leaderboard_refresh", "monthly", date(2026, 1, 1)
    )
    assert refresh_key != key


@pytest.mark.asyncio
async def test_leaderboard_snapshot_unique_per_agent_period(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R51 (migration 0037): duplicate (period_type, period_start,
    agent_id) snapshot rows are rejected by the DB backstop."""
    agent_data = await register_user(client)
    agent_id = UUID(agent_data["user"]["id"])
    period_start = date(2026, 1, 1)

    db_session.add(LeaderboardSnapshot(
        agent_id=agent_id,
        rank=1,
        volume_cents=100_000,
        period_type=PeriodType.MONTHLY,
        period_start=period_start,
        snapshot_at=datetime.now(UTC),
        is_final=False,
    ))
    await db_session.commit()

    db_session.add(LeaderboardSnapshot(
        agent_id=agent_id,
        rank=2,
        volume_cents=200_000,
        period_type=PeriodType.MONTHLY,
        period_start=period_start,
        snapshot_at=datetime.now(UTC),
        is_final=False,
    ))
    with pytest.raises(IntegrityError) as exc:
        await db_session.commit()
    await db_session.rollback()
    assert "uq_leaderboard_period_agent" in str(exc.value)
