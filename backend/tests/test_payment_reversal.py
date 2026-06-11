# =============================================================================
# CBSHOME Backend -- Payment Reversal Tests (Sprint 5.3)
# =============================================================================
#
# Tests cover:
#   1:  Reverse frozen payment -> 200, mirror entries created, BOTH
#       original and mirror reversed (R47), balances zeroed
#   2:  Reverse confirmed payment -> 200 (fraud dispute path)
#   3:  Reverse already reversed payment -> 400 (terminal status)
#   4:  Reverse failed payment -> 400 (terminal status)
#   5:  Reverse non-existent payment -> 404
#   6:  Reverse without payment_review permission -> 403
#   7:  R47 money assertion: reversing an UNSPENT confirmed deposit
#       leaves the user's spendable balance at exactly 0 (the pre-R47
#       confirmed mirror left it at -amount: double debit)
#   8:  R47 invariants: after reversal no CONFIRMED entries reference
#       the payment (S-08) and the original+mirror pair sums to 0 (S-01)
#   9:  R-2.2 groundwork: frozen deposit -> purchase -> chargeback pins
#       the full-unwind behaviour (balance 0, no debt, 4 REVERSED rows)
#       and the open hole: Purchase stays ACTIVE, buyer keeps units
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
from app.modules.ledgers.service import get_active_balance, record_active_ledger
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

    # R47: the mirror is REVERSED too -- a CONFIRMED mirror was the
    # double-debit bug (balance excludes reversed originals AND
    # subtracted the confirmed mirror).
    assert mirror.status == LedgerStatus.REVERSED
    assert mirror.amount_cents == -10050
    assert mirror.reason.endswith(":reversal")

    # Net spendable effect: the frozen deposit simply disappears.
    balance = await get_active_balance(db_session, user_id)
    assert balance["frozen"] == 0
    assert balance["confirmed"] == 0


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


@pytest.mark.asyncio
async def test_reverse_unspent_deposit_balance_zero(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R47 money assertion: reversing an unspent CONFIRMED deposit
    leaves the user's spendable balance at exactly 0.

    This is the assertion whose absence let the double-debit ship:
    pre-R47 the confirmed mirror left the user at -10050 (the original
    was excluded as reversed AND the mirror was subtracted).
    """
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(
        user_id, db_session, status=PaymentStatus.CONFIRMED
    )

    before = await get_active_balance(db_session, user_id)
    assert before["confirmed"] == 10050

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200

    db_session.expire_all()
    after = await get_active_balance(db_session, user_id)
    assert after["confirmed"] == 0, (
        f"unspent reversed deposit must net to 0, got {after['confirmed']} "
        "(negative means the double-debit regressed)"
    )
    assert after["frozen"] == 0


@pytest.mark.asyncio
async def test_reverse_invariants_s08_s01_pair(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R47 invariant pins: after a reversal,

    * S-08: NO entry referencing the payment is CONFIRMED (the pre-R47
      confirmed mirror tripped this semaphore on every reversal);
    * S-01 (pair-local): original + mirror sum to exactly 0, so the
      global all-statuses ledger sum is unchanged by the reversal.
    """
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200

    db_session.expire_all()
    entries = (await db_session.execute(
        select(ActiveLedger)
        .where(ActiveLedger.origin_payment_id == payment_id)
    )).scalars().all()
    assert len(entries) == 2  # original + mirror

    # S-08: no confirmed rows reference the reversed payment.
    assert all(e.status == LedgerStatus.REVERSED for e in entries), (
        "every entry of a reversed payment must be status=reversed"
    )

    # S-01 pair: the reversal is net-zero in the all-statuses sum.
    assert sum(e.amount_cents for e in entries) == 0


@pytest.mark.asyncio
async def test_reverse_spent_frozen_deposit_unwinds_purchase_debit(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R-2.2 groundwork: frozen deposit -> purchase -> chargeback.

    Pins the CURRENT behaviour of the spent-deposit path (the one the
    pre-R47 header described wrongly):

      * frozen-funded purchase debits inherit the deposit's
        origin_payment_id (compute_frozen_context), so the reversal
        captures BOTH rows -- deposit credit and purchase debit unwind
        together, every entry ends up REVERSED;
      * spendable balance lands at exactly 0 -- NO debt is recorded;
      * Purchase.status stays ACTIVE -- the buyer KEEPS the units.

    The last assertion is the open R-2.2 hole, pinned deliberately:
    when purchase chargeback lands, flip it to PurchaseStatus.REVERSED
    and this test becomes the regression guard for the full unwind.
    """
    from sqlalchemy import select as sa_select

    from app.modules.ledgers.service import record_active_ledger as _ral
    from app.modules.products.models import Product
    from app.modules.purchases.constants import (
        PurchaseLegalBasis,
        PurchaseStatus as PStatus,
    )
    from app.modules.purchases.models import Purchase

    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    # Spend the frozen deposit: minimal Purchase against any seeded
    # storefront product + the ledger debit shaped exactly like
    # compute_frozen_context writes it -- reason "purchase:{id}" and
    # the deposit's origin_payment_id inherited.
    product = (
        await db_session.execute(sa_select(Product).limit(1))
    ).scalar_one_or_none()
    assert product is not None, "storefront seed must run before tests"

    purchase = Purchase(
        investor_id=user_id,
        product_id=product.id,
        company_id=product.company_id,
        legal_basis=PurchaseLegalBasis.SALE,
        units=1,
        paid_cents=10050,
        price_per_unit_cents=10050,
        status=PStatus.ACTIVE,
    )
    db_session.add(purchase)
    await db_session.flush()

    await _ral(
        db_session,
        user_id=user_id,
        amount_cents=-10050,
        status=LedgerStatus.FROZEN,
        reason=f"purchase:{purchase.id}",
        frozen_until=datetime.now(UTC) + timedelta(hours=24),
        origin_payment_id=payment_id,
    )
    await db_session.commit()
    purchase_id = purchase.id

    # Sanity: deposit +10050 and debit -10050 net to zero pre-reversal.
    before = await get_active_balance(db_session, user_id)
    assert before["frozen"] == 0
    assert before["confirmed"] == 0

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback after spending"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Both captured rows count: |+10050| + |-10050|.
    assert body["total_reversed_cents"] == 20100
    assert body["active_entries_reversed"] == 2

    db_session.expire_all()

    # Full unwind: 2 originals + 2 mirrors, all REVERSED, sum 0.
    entries = (await db_session.execute(
        sa_select(ActiveLedger)
        .where(ActiveLedger.origin_payment_id == payment_id)
    )).scalars().all()
    assert len(entries) == 4
    assert all(e.status == LedgerStatus.REVERSED for e in entries)
    assert sum(e.amount_cents for e in entries) == 0

    # No debt recorded: balance is 0, not negative.
    after = await get_active_balance(db_session, user_id)
    assert after["frozen"] == 0
    assert after["confirmed"] == 0

    # THE open R-2.2 hole, pinned on purpose: the buyer keeps the
    # units. Flip this to PStatus.REVERSED when purchase chargeback
    # lands.
    p = (await db_session.execute(
        sa_select(Purchase).where(Purchase.id == purchase_id)
    )).scalar_one()
    assert p.status == PStatus.ACTIVE
