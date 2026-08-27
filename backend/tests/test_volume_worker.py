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
#   3: _distribute_pool -> commission.credited on the outbox, one per
#      credited agent, keyed by that agent's VolumePayout row (TASK-24
#      batch 3, 2026-08-27). FIRST integration coverage of
#      _distribute_pool itself -- it had none before this; the setup
#      below is the minimum real state the function reads (a real
#      Purchase row for the pool total, a manually-seeded snapshot for
#      ranking, the platform user's existing passive balance topped up
#      directly), not a claim that the payout MATH is exhaustively
#      covered elsewhere.
#   4: comms NOT configured -> no outbox row
#
# Shared dev DB note: test 2 builds its key from a freshly registered
# agent (unique UUID per run), so runs never collide on the constraint.
# =============================================================================

import uuid
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import OutboxEvent
from app.core.events.service import EVENT_NOTIFICATION_REQUEST
from app.modules.commissions.constants import PeriodType
from app.modules.commissions.models import LeaderboardSnapshot, VolumePayout
from app.modules.commissions.worker import _distribute_pool, _period_lock_key
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger, record_passive_ledger
from app.modules.users.models import User, UserRole
from tests.helpers import auth_headers, create_admin_user, register_user


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


# ---------------------------------------------------------------------------
# 3-4. Notification emission (TASK-24 batch 3)
# ---------------------------------------------------------------------------


async def _notification_events(session: AsyncSession) -> list[OutboxEvent]:
    """Every notification_request event on the outbox, oldest first."""
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.event_type == EVENT_NOTIFICATION_REQUEST)
        .order_by(OutboxEvent.id)
    )
    return list(result.scalars().all())


async def _make_one_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> int:
    """Minimal company + product + funded investor + one real instant
    purchase, so _get_total_purchases_cents has a non-zero pool to find.
    Local, not imported from test_purchases.py -- this file's own
    convention (test_purchases.py's own helpers are local too).

    Returns paid_cents of the purchase created.
    """
    _, admin_token = await create_admin_user(client, db_session)

    company_resp = await client.post(
        "/api/v1/staff/companies",
        json={
            "email": f"vwco_{uuid.uuid4().hex[:12]}@example.com",
            "password": "companypass123",
            "name": "Volume Worker Test Co",
            "description": "test",
            "price_per_unit_cents": 10000,
            "distribution_config": {
                "company_pct": 0.65,
                "agent_levels": [0.10, 0.03, 0.01],
            },
            "total_supply": 1_000_000,
            "shares_per_option": 1,
        },
        headers=auth_headers(admin_token),
    )
    assert company_resp.status_code == 201, company_resp.text
    company = company_resp.json()

    pool_resp = await client.post(
        f"/api/v1/staff/companies/{company['id']}/pool",
        json={"equity_percent": "100.0"},
        headers=auth_headers(admin_token),
    )
    assert pool_resp.status_code == 201, pool_resp.text

    product_resp = await client.post(
        "/api/v1/staff/products",
        json={
            "company_id": company["id"],
            "name": "Volume Worker Test Package",
            "package_size": 100,
        },
        headers=auth_headers(admin_token),
    )
    assert product_resp.status_code == 201, product_resp.text
    product = product_resp.json()

    await client.patch(
        f"/api/v1/staff/companies/{company['id']}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )
    await client.patch(
        f"/api/v1/staff/products/{product['id']}/status",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )

    inv_data = await register_user(client)
    inv_token = inv_data["session_token"]
    inv_id = UUID(inv_data["user"]["id"])
    stmt = select(User).where(User.id == inv_id)
    result = await db_session.execute(stmt)
    investor = result.scalar_one()
    investor.kyc_status = "approved"
    await db_session.flush()
    await record_active_ledger(
        db_session,
        user_id=inv_id,
        amount_cents=2_000_000,
        status=LedgerStatus.CONFIRMED,
        reason="test:credit",
    )
    await db_session.commit()

    purchase_resp = await client.post(
        f"/api/v1/products/{product['id']}/purchase",
        json={},
        headers=auth_headers(inv_token),
    )
    assert purchase_resp.status_code == 201, purchase_resp.text
    return purchase_resp.json()[0]["paid_cents"]


@pytest.mark.asyncio
async def test_distribute_pool_emits_commission_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_distribute_pool credits an agent -> commission.credited on the
    outbox, targeting that agent, keyed by their VolumePayout row."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")

    await _make_one_purchase(client, db_session)

    agent_data = await register_user(client)
    agent_id = UUID(agent_data["user"]["id"])

    period_start = date(2020, 1, 1)
    period_end = date(2030, 1, 1)

    db_session.add(LeaderboardSnapshot(
        agent_id=agent_id,
        rank=1,
        volume_cents=1_000_000,
        period_type=PeriodType.MONTHLY,
        period_start=period_start,
        snapshot_at=datetime.now(UTC),
        is_final=False,
    ))
    await db_session.flush()

    # Top up the platform user's passive balance so the payout's
    # sufficiency check (available >= pool_cents) passes -- the pool
    # itself is a fraction of the one purchase's paid_cents, so a
    # generous top-up covers it without computing the exact figure.
    platform_id = (
        await db_session.execute(
            select(User.id).where(User.role == UserRole.PLATFORM)
        )
    ).scalar_one()
    await record_passive_ledger(
        db_session,
        user_id=platform_id,
        amount_cents=5_000_000,
        status=LedgerStatus.CONFIRMED,
        reason="test:platform_topup",
    )
    await db_session.commit()

    before = len(await _notification_events(db_session))

    await _distribute_pool(
        session=db_session,
        period_type=PeriodType.MONTHLY,
        period_start=period_start,
        period_end=period_end,
        bonus_bp=200,  # 2.00%
        top_n=20,
    )
    await db_session.commit()

    payout = (
        await db_session.execute(
            select(VolumePayout).where(VolumePayout.agent_id == agent_id)
        )
    ).scalar_one()

    events = await _notification_events(db_session)
    assert len(events) == before + 1
    payload = events[-1].payload
    assert payload["type"] == "commission.credited"
    assert payload["target_type"] == "user"
    assert payload["target_value"] == str(agent_id)
    assert payload["idempotency_key"] == f"commission-credit:{payout.id}"


@pytest.mark.asyncio
async def test_distribute_pool_without_comms_emits_nothing(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No comms address -> no outbox row, same gate as every other
    emitter in this tree."""
    monkeypatch.setattr(settings, "comms_api_url", "")

    await _make_one_purchase(client, db_session)

    agent_data = await register_user(client)
    agent_id = UUID(agent_data["user"]["id"])

    period_start = date(2020, 1, 1)
    period_end = date(2030, 1, 1)

    db_session.add(LeaderboardSnapshot(
        agent_id=agent_id,
        rank=1,
        volume_cents=1_000_000,
        period_type=PeriodType.QUARTERLY,
        period_start=period_start,
        snapshot_at=datetime.now(UTC),
        is_final=False,
    ))
    await db_session.flush()

    platform_id = (
        await db_session.execute(
            select(User.id).where(User.role == UserRole.PLATFORM)
        )
    ).scalar_one()
    await record_passive_ledger(
        db_session,
        user_id=platform_id,
        amount_cents=5_000_000,
        status=LedgerStatus.CONFIRMED,
        reason="test:platform_topup",
    )
    await db_session.commit()

    before = len(await _notification_events(db_session))

    await _distribute_pool(
        session=db_session,
        period_type=PeriodType.QUARTERLY,
        period_start=period_start,
        period_end=period_end,
        bonus_bp=200,
        top_n=20,
    )
    await db_session.commit()

    assert len(await _notification_events(db_session)) == before
