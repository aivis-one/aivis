# =============================================================================
# AIVIS.ONE Backend -- Payment Confirmation Tests (Sprint 5.3)
# =============================================================================
#
# Tests cover:
#   1:  Frozen payment + active_ledger with expired frozen_until -> both confirmed
#   2:  Frozen payment with future frozen_until -> stays frozen
#   3:  Multiple frozen payments, mixed expiry -> only expired ones confirmed
#   4:  Frozen passive_ledger with expired frozen_until -> confirmed
#   5:  Already confirmed payment -> not touched by daemon
#   6:  Reversed payment -> not touched by daemon
#   7:  Daemon runs with no frozen entries -> no errors
#   8:  Payment confirmed but active_ledger still frozen (different frozen_until)
#       -> ledger confirmed independently
#
# Email prefix: "s53c_" -- unique to this test file, cleaned up in fixture.
#
# NOTE: Tests call run_confirmation_batch() directly (not the daemon loop).
#       The function creates its own session, so test db_session must commit
#       setup data before calling it, then re-query to verify results.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import OutboxEvent
from app.core.events.service import EVENT_NOTIFICATION_REQUEST
from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.payments.constants import PaymentStatus, PaymentType
from app.modules.payments.models import Payment
from tests.helpers import register_user



async def _create_user(client: AsyncClient) -> UUID:
    """Helper: register a user and return their UUID."""
    data = await register_user(
        client
    )
    return UUID(data["user"]["id"])


def _make_payment(
    user_id: UUID,
    *,
    status: str = PaymentStatus.FROZEN,
    frozen_until: datetime | None = None,
) -> Payment:
    """Helper: create a Payment ORM object (not flushed)."""
    return Payment(
        user_id=user_id,
        amount_cents=10000,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider="crypto_usdt_trc20",
        status=status,
        frozen_until=frozen_until,
        provider_data={"tx_hash": f"0x_test_{uuid4().hex[:8]}"},
    )


def _make_active_ledger(
    user_id: UUID,
    *,
    amount_cents: int = 10000,
    status: str = LedgerStatus.FROZEN,
    frozen_until: datetime | None = None,
    origin_payment_id: UUID | None = None,
    reason: str = "deposit:crypto:0x_test",
) -> ActiveLedger:
    """Helper: create an ActiveLedger ORM object (not flushed)."""
    return ActiveLedger(
        user_id=user_id,
        amount_cents=amount_cents,
        status=status,
        frozen_until=frozen_until,
        origin_payment_id=origin_payment_id,
        reason=reason,
    )


def _make_passive_ledger(
    user_id: UUID,
    *,
    amount_cents: int = 5000,
    status: str = LedgerStatus.FROZEN,
    frozen_until: datetime | None = None,
    origin_payment_id: UUID | None = None,
    reason: str = "saga:company_revenue:test",
) -> PassiveLedger:
    """Helper: create a PassiveLedger ORM object (not flushed)."""
    return PassiveLedger(
        user_id=user_id,
        amount_cents=amount_cents,
        status=status,
        frozen_until=frozen_until,
        origin_payment_id=origin_payment_id,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_expired_payment_and_active_ledger(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Frozen payment + active_ledger with expired frozen_until -> both confirmed."""
    user_id = await _create_user(client)
    past = datetime.now(UTC) - timedelta(hours=1)

    payment = _make_payment(user_id, frozen_until=past)
    db_session.add(payment)
    await db_session.flush()

    ledger = _make_active_ledger(
        user_id,
        frozen_until=past,
        origin_payment_id=payment.id,
    )
    db_session.add(ledger)
    await db_session.commit()

    payment_id = payment.id
    ledger_id = ledger.id

    # Run confirmation batch (uses its own session).
    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    # Re-query with test session to verify.
    db_session.expire_all()

    p = (await db_session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one()
    assert p.status == PaymentStatus.CONFIRMED

    al = (await db_session.execute(
        select(ActiveLedger).where(ActiveLedger.id == ledger_id)
    )).scalar_one()
    assert al.status == LedgerStatus.CONFIRMED


@pytest.mark.asyncio
async def test_frozen_future_not_confirmed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Frozen payment with future frozen_until -> stays frozen."""
    user_id = await _create_user(client)
    future = datetime.now(UTC) + timedelta(hours=24)

    payment = _make_payment(user_id, frozen_until=future)
    db_session.add(payment)
    await db_session.flush()

    ledger = _make_active_ledger(
        user_id,
        frozen_until=future,
        origin_payment_id=payment.id,
    )
    db_session.add(ledger)
    await db_session.commit()

    payment_id = payment.id
    ledger_id = ledger.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    db_session.expire_all()

    p = (await db_session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one()
    assert p.status == PaymentStatus.FROZEN

    al = (await db_session.execute(
        select(ActiveLedger).where(ActiveLedger.id == ledger_id)
    )).scalar_one()
    assert al.status == LedgerStatus.FROZEN


# ---------------------------------------------------------------------------
# Notification emission (batch 6, 2026-08-28)
# ---------------------------------------------------------------------------


async def _notification_events(session: AsyncSession) -> list[OutboxEvent]:
    """Every notification_request event on the outbox, oldest first."""
    result = await session.execute(
        select(OutboxEvent)
        .where(OutboxEvent.event_type == EVENT_NOTIFICATION_REQUEST)
        .order_by(OutboxEvent.id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_confirm_expired_payment_emits_deposit_confirmed_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirming a frozen payment -> deposit.confirmed on the outbox,
    keyed by the payment's own id (shared test DB: select THIS payment's
    row by idempotency key, never an absolute count)."""
    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    user_id = await _create_user(client)
    past = datetime.now(UTC) - timedelta(hours=1)

    payment = _make_payment(user_id, frozen_until=past)
    db_session.add(payment)
    await db_session.commit()
    payment_id = payment.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    events = await _notification_events(db_session)
    matches = [
        e for e in events
        if e.payload.get("idempotency_key") == f"deposit-confirmed:{payment_id}"
    ]
    assert len(matches) == 1
    payload = matches[0].payload
    assert payload["type"] == "deposit.confirmed"
    assert payload["target_type"] == "user"
    assert payload["target_value"] == str(user_id)
    assert "100.00" in payload["body"]


@pytest.mark.asyncio
async def test_confirm_without_comms_emits_no_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No comms address -> no outbox row, same gate as every other
    emitter in this tree."""
    monkeypatch.setattr(settings, "comms_api_url", "")
    user_id = await _create_user(client)
    past = datetime.now(UTC) - timedelta(hours=1)

    payment = _make_payment(user_id, frozen_until=past)
    db_session.add(payment)
    await db_session.commit()
    payment_id = payment.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    events = await _notification_events(db_session)
    matches = [
        e for e in events
        if e.payload.get("idempotency_key") == f"deposit-confirmed:{payment_id}"
    ]
    assert len(matches) == 0


@pytest.mark.asyncio
async def test_mixed_expiry_only_expired_confirmed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Multiple frozen payments, mixed expiry -> only expired ones confirmed."""
    user_id = await _create_user(client)
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(hours=24)

    p_expired = _make_payment(user_id, frozen_until=past)
    p_active = _make_payment(user_id, frozen_until=future)
    db_session.add_all([p_expired, p_active])
    await db_session.commit()

    expired_id = p_expired.id
    active_id = p_active.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    db_session.expire_all()

    p1 = (await db_session.execute(
        select(Payment).where(Payment.id == expired_id)
    )).scalar_one()
    assert p1.status == PaymentStatus.CONFIRMED

    p2 = (await db_session.execute(
        select(Payment).where(Payment.id == active_id)
    )).scalar_one()
    assert p2.status == PaymentStatus.FROZEN


@pytest.mark.asyncio
async def test_confirm_expired_passive_ledger(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Frozen passive_ledger with expired frozen_until -> confirmed."""
    user_id = await _create_user(client)
    past = datetime.now(UTC) - timedelta(hours=1)

    pl = _make_passive_ledger(user_id, frozen_until=past)
    db_session.add(pl)
    await db_session.commit()

    pl_id = pl.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    db_session.expire_all()

    entry = (await db_session.execute(
        select(PassiveLedger).where(PassiveLedger.id == pl_id)
    )).scalar_one()
    assert entry.status == LedgerStatus.CONFIRMED


@pytest.mark.asyncio
async def test_already_confirmed_not_touched(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Already confirmed payment -> not touched by daemon."""
    user_id = await _create_user(client)

    payment = _make_payment(
        user_id,
        status=PaymentStatus.CONFIRMED,
        frozen_until=None,
    )
    db_session.add(payment)
    await db_session.commit()

    payment_id = payment.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    db_session.expire_all()

    p = (await db_session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one()
    assert p.status == PaymentStatus.CONFIRMED


@pytest.mark.asyncio
async def test_reversed_not_touched(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reversed payment -> not touched by daemon."""
    user_id = await _create_user(client)

    payment = _make_payment(
        user_id,
        status=PaymentStatus.REVERSED,
        frozen_until=None,
    )
    db_session.add(payment)
    await db_session.commit()

    payment_id = payment.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    db_session.expire_all()

    p = (await db_session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one()
    assert p.status == PaymentStatus.REVERSED


@pytest.mark.asyncio
async def test_empty_batch_no_errors(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Daemon runs with no frozen entries -> no errors."""
    from app.modules.payments.confirmation import run_confirmation_batch
    # Should not raise.
    await run_confirmation_batch()


@pytest.mark.asyncio
async def test_independent_frozen_until_payment_vs_ledger(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Payment confirmed but active_ledger still frozen (different frozen_until).

    Daemon confirms each record based on its own frozen_until, not linked.
    """
    user_id = await _create_user(client)
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(hours=24)

    # Payment expired, ledger not yet.
    payment = _make_payment(user_id, frozen_until=past)
    db_session.add(payment)
    await db_session.flush()

    ledger = _make_active_ledger(
        user_id,
        frozen_until=future,
        origin_payment_id=payment.id,
    )
    db_session.add(ledger)
    await db_session.commit()

    payment_id = payment.id
    ledger_id = ledger.id

    from app.modules.payments.confirmation import run_confirmation_batch
    await run_confirmation_batch()

    db_session.expire_all()

    p = (await db_session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one()
    assert p.status == PaymentStatus.CONFIRMED

    al = (await db_session.execute(
        select(ActiveLedger).where(ActiveLedger.id == ledger_id)
    )).scalar_one()
    assert al.status == LedgerStatus.FROZEN
