# =============================================================================
# CBSHOME Backend -- Payment Reversal Tests (Sprint 5.3)
# =============================================================================
#
# Tests cover:
#   1:  Reverse frozen payment -> 200, mirror entries created, originals reversed
#   2:  Reverse confirmed payment -> 200 (fraud dispute path)
#   3:  Reverse already reversed payment -> 400 (terminal status)
#   4:  Reverse failed payment -> 400 (terminal status)
#   5:  Reverse non-existent payment -> 404
#   6:  Reverse without payment_review permission -> 403
#
# Email prefix: "s53r_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import ActiveLedger, LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.payments.constants import PaymentStatus, PaymentType
from app.modules.payments.models import Payment
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)



async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(
        client, db_session
    )
    return token


async def _create_investor(client: AsyncClient) -> UUID:
    """Helper: register investor and return their UUID."""
    data = await register_user(
        client
    )
    return UUID(data["user"]["id"])


async def _create_frozen_payment_with_ledger(
    user_id: UUID,
    db_session: AsyncSession,
    *,
    status: str = PaymentStatus.FROZEN,
) -> UUID:
    """Helper: create Payment + ActiveLedger entry, return payment_id."""
    frozen_until = datetime.now(UTC) + timedelta(hours=24)
    tx_hash = f"0x_rev_{uuid4().hex[:8]}"

    payment = Payment(
        user_id=user_id,
        amount_cents=10050,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider="crypto_usdt_trc20",
        status=status,
        frozen_until=frozen_until if status == PaymentStatus.FROZEN else None,
        provider_data={"tx_hash": tx_hash},
    )
    db_session.add(payment)
    await db_session.flush()

    ledger_status = (
        LedgerStatus.FROZEN if status == PaymentStatus.FROZEN
        else LedgerStatus.CONFIRMED
    )
    await record_active_ledger(
        db_session,
        user_id=user_id,
        amount_cents=10050,
        status=ledger_status,
        reason=f"deposit:crypto:{tx_hash}",
        frozen_until=frozen_until if ledger_status == LedgerStatus.FROZEN else None,
        origin_payment_id=payment.id,
    )
    await db_session.commit()

    return payment.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reverse_frozen_payment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reverse frozen payment -> 200, mirror entries, originals reversed."""
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback from bank"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_reversed_cents"] == 10050
    assert body["active_entries_reversed"] == 1
    assert body["passive_entries_reversed"] == 0

    # Verify payment status.
    db_session.expire_all()
    p = (await db_session.execute(
        select(Payment).where(Payment.id == payment_id)
    )).scalar_one()
    assert p.status == PaymentStatus.REVERSED

    # Verify original active_ledger entry is reversed.
    entries = (await db_session.execute(
        select(ActiveLedger)
        .where(ActiveLedger.origin_payment_id == payment_id)
        .order_by(ActiveLedger.created_at)
    )).scalars().all()
    assert len(entries) == 2  # original + mirror

    original = entries[0]
    mirror = entries[1]

    assert original.status == LedgerStatus.REVERSED
    assert original.amount_cents == 10050

    assert mirror.status == LedgerStatus.CONFIRMED
    assert mirror.amount_cents == -10050
    assert mirror.reason.endswith(":reversal")


@pytest.mark.asyncio
async def test_reverse_confirmed_payment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reverse confirmed payment -> 200 (fraud dispute)."""
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(
        user_id, db_session, status=PaymentStatus.CONFIRMED
    )

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "fraud dispute"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_reversed_cents"] == 10050
    assert body["active_entries_reversed"] == 1


@pytest.mark.asyncio
async def test_reverse_already_reversed_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reverse already reversed payment -> 400."""
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    # First reversal.
    resp1 = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp1.status_code == 200

    # Second reversal -> should fail.
    resp2 = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_reverse_failed_payment_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reverse failed payment -> 400."""
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)

    # Create a failed payment (no ledger entries needed).
    payment = Payment(
        user_id=user_id,
        amount_cents=5000,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider="crypto_usdt_trc20",
        status=PaymentStatus.FAILED,
        provider_data={"tx_hash": f"0x_fail_{uuid4().hex[:8]}"},
    )
    db_session.add(payment)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/staff/payments/{payment.id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reverse_nonexistent_payment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reverse non-existent payment -> 404."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        f"/api/v1/staff/payments/{uuid4()}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reverse_without_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reverse without payment_review permission -> 403."""
    admin_token = await _admin_token(client, db_session)

    # Email held in a local so the later login_user call hits the same
    # account that register_user just created.
    noperm_email = f"noperm_{uuid4().hex[:12]}@example.com"
    staff_data = await register_user(
        client, email=noperm_email
    )
    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": staff_data["user"]["id"]},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    profile_id = resp.json()["id"]

    # Remove payment_review permission.
    await client.patch(
        f"/api/v1/staff/users/{profile_id}/permissions",
        json={"payment_review": False},
        headers=auth_headers(admin_token),
    )

    # Re-login as restricted staff.
    from tests.helpers import login_user
    login_data = await login_user(
        client, email=noperm_email
    )
    restricted_token = login_data["session_token"]

    resp2 = await client.post(
        f"/api/v1/staff/payments/{uuid4()}/reverse",
        json={},
        headers=auth_headers(restricted_token),
    )
    assert resp2.status_code == 403
