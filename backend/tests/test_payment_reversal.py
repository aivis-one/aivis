# =============================================================================
# AIVIS.ONE Backend -- Payment Reversal Tests (Sprint 5.3)
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
#   9:  R-2.2 Block A: frozen deposit -> purchase -> chargeback unwinds
#       the asset too -- Purchase flips to REVERSED, pool consumption
#       drops by the purchase units, purchases_reversed == 1
#   10: plain deposit reversal reports purchases_reversed == 0
#   11: R-2.2 commission clawback pin: a frozen-funded commission
#       credit (origin_payment_id inherited) is unwound by the payment
#       reversal -- agent passive balance returns to 0
#
# Email prefix: "s53r_" -- unique to this test file, cleaned up in fixture.
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
    assert body["purchases_reversed"] == 0  # no purchase debit captured

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

    R-2.2 Block A regression guard (formerly pinned the open hole):

      * frozen-funded purchase debits inherit the deposit's
        origin_payment_id (compute_frozen_context), so the reversal
        captures BOTH rows -- deposit credit and purchase debit unwind
        together, every entry ends up REVERSED;
      * spendable balance lands at exactly 0 -- NO debt is recorded;
      * the ASSET unwinds too: Purchase flips to REVERSED, the units
        leave pool consumption (get_pool_consumed counts ACTIVE only),
        and the response reports purchases_reversed == 1.
    """
    from sqlalchemy import select as sa_select

    from app.modules.ledgers.service import record_active_ledger as _ral
    from app.modules.pools.service import get_pool_consumed
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

    # Pool consumption baseline AFTER the purchase exists (shared dev
    # DB -- only the delta is assertable). company_id is captured into
    # a plain variable HERE: after db_session.expire_all() below the
    # `product` ORM object is expired and attribute access would
    # trigger a lazy refresh outside the greenlet (MissingGreenlet).
    company_id = product.company_id
    consumed_with_purchase = await get_pool_consumed(
        company_id, db_session
    )

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
    assert body["purchases_reversed"] == 1

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

    # R-2.2 Block A: the asset unwinds with the money.
    p = (await db_session.execute(
        sa_select(Purchase).where(Purchase.id == purchase_id)
    )).scalar_one()
    assert p.status == PStatus.REVERSED

    # Units returned to the pool: consumption dropped by exactly the
    # purchase's units.
    consumed_after = await get_pool_consumed(company_id, db_session)
    assert consumed_after == consumed_with_purchase - p.units


@pytest.mark.asyncio
async def test_reverse_payment_claws_back_frozen_funded_commission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """R-2.2 pin: commissions funded by a frozen deposit are clawed
    back by the payment reversal automatically.

    purchases/engine.py writes the deposit's origin_payment_id into
    EVERY entry of the purchase transaction -- including the agent's
    passive commission credit -- so step 4 of reverse_payment captures
    it and the passive loop unwinds it. This test seeds the commission
    entry in exactly that shape and asserts the clawback.
    """
    from uuid import uuid4 as _uuid4

    from app.modules.ledgers.service import (
        get_passive_balance,
        record_passive_ledger,
    )
    from app.modules.ledgers.models import PassiveLedger

    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    agent_id = await _create_investor(client)  # any user can hold passive
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    # Commission credit shaped like ReferralProcessor output for a
    # frozen-funded purchase: origin_payment_id inherited, frozen.
    await record_passive_ledger(
        db_session,
        user_id=agent_id,
        amount_cents=500,
        status=LedgerStatus.FROZEN,
        reason=f"commission:l1:{agent_id}:{_uuid4()}",
        frozen_until=datetime.now(UTC) + timedelta(hours=24),
        origin_payment_id=payment_id,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["passive_entries_reversed"] == 1
    assert body["total_reversed_cents"] == 10050 + 500

    db_session.expire_all()

    # Clawback: the agent's passive balance is back to zero, both the
    # credit and its mirror are REVERSED.
    balance = await get_passive_balance(db_session, agent_id)
    assert balance["frozen"] == 0
    assert balance["confirmed"] == 0

    from sqlalchemy import select as sa_select
    entries = (await db_session.execute(
        sa_select(PassiveLedger).where(
            PassiveLedger.origin_payment_id == payment_id
        )
    )).scalars().all()
    assert len(entries) == 2
    assert all(e.status == LedgerStatus.REVERSED for e in entries)
    assert sum(e.amount_cents for e in entries) == 0


# ---------------------------------------------------------------------------
# Tranche-unwind (boss-locked semantics; closes the R-2.2 accepted risk)
# ---------------------------------------------------------------------------


async def _build_plan_with_paid_tranche(
    user_id: UUID,
    payment_id: UUID,
    db_session: AsyncSession,
    *,
    plan_status: str,
):
    """Scaffold: plan + PAID tranche (with Purchase) + SCHEDULED sibling,
    funded by the given frozen payment. Mirrors the shapes pay_tranche /
    compute_frozen_context write: tranche debit reason
    "installment:tranche:{id}" with the deposit's origin_payment_id.

    Returns (plan, paid_tranche, sibling, purchase).
    """
    from datetime import date as _date

    from sqlalchemy import select as sa_select

    from app.modules.installments.constants import (
        InstallmentPlanStatus,
        InstallmentTrancheStatus,
    )
    from app.modules.installments.models import (
        InstallmentPlan,
        InstallmentTranche,
    )
    from app.modules.ledgers.service import record_active_ledger as _ral
    from app.modules.products.models import Product, ProductInstallment
    from app.modules.purchases.constants import (
        PurchaseLegalBasis,
        PurchaseStatus as PStatus,
    )
    from app.modules.purchases.models import Purchase

    # Any seeded installment template anchors the FK chain; use its
    # product/company so the rows are mutually consistent.
    template = (
        await db_session.execute(sa_select(ProductInstallment).limit(1))
    ).scalar_one_or_none()
    assert template is not None, "storefront seed must run before tests"
    product = (
        await db_session.execute(
            sa_select(Product).where(Product.id == template.product_id)
        )
    ).scalar_one()

    plan = InstallmentPlan(
        investor_id=user_id,
        product_id=product.id,
        product_installment_id=template.id,
        company_id=product.company_id,
        plan_config_snapshot={"tranches": [], "bonus_units": 0},
        total_price_cents=10050,
        total_units=2,
        price_per_unit_cents=5025,
        status=plan_status,
    )
    if plan_status == InstallmentPlanStatus.COMPLETED:
        plan.completed_at = datetime.now(UTC)
    db_session.add(plan)
    await db_session.flush()

    purchase = Purchase(
        investor_id=user_id,
        product_id=product.id,
        company_id=product.company_id,
        legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE,
        units=1,
        paid_cents=10050,
        price_per_unit_cents=10050,
        status=PStatus.ACTIVE,
    )
    db_session.add(purchase)
    await db_session.flush()

    paid_tranche = InstallmentTranche(
        plan_id=plan.id,
        number=1,
        due_date=_date.today(),
        amount_cents=10050,
        units_unlocked=1,
        status=InstallmentTrancheStatus.PAID,
        paid_at=datetime.now(UTC),
        purchase_id=purchase.id,
    )
    sibling = InstallmentTranche(
        plan_id=plan.id,
        number=2,
        due_date=_date.today(),
        amount_cents=10050,
        units_unlocked=1,
        status=(
            InstallmentTrancheStatus.SCHEDULED
            if plan_status == InstallmentPlanStatus.ACTIVE
            else InstallmentTrancheStatus.PAID
        ),
        purchase_id=None,
    )
    db_session.add_all([paid_tranche, sibling])
    await db_session.flush()

    # The frozen-funded tranche debit, exactly as pay_tranche writes it.
    await _ral(
        db_session,
        user_id=user_id,
        amount_cents=-10050,
        status=LedgerStatus.FROZEN,
        reason=f"installment:tranche:{paid_tranche.id}",
        frozen_until=datetime.now(UTC) + timedelta(hours=24),
        origin_payment_id=payment_id,
    )
    await db_session.commit()
    return plan, paid_tranche, sibling, purchase


@pytest.mark.asyncio
async def test_reverse_payment_unwinds_tranche_and_defaults_plan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tranche-unwind on an ACTIVE plan (boss-locked p.1-3):

      * the tranche's Purchase flips to REVERSED (units leave the
        portfolio/pool implicitly, same as the instant unwind);
      * the tranche goes to terminal REVERSED;
      * the plan defaults: sibling SCHEDULED tranche -> CANCELLED,
        plan -> DEFAULTED with defaulted_at set;
      * the reversal summary reports the unwind.
    """
    from sqlalchemy import select as sa_select

    from app.modules.installments.constants import (
        InstallmentPlanStatus,
        InstallmentTrancheStatus,
    )
    from app.modules.installments.models import (
        InstallmentPlan,
        InstallmentTranche,
    )
    from app.modules.purchases.constants import PurchaseStatus as PStatus
    from app.modules.purchases.models import Purchase

    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    plan, paid_tranche, sibling, purchase = (
        await _build_plan_with_paid_tranche(
            user_id, payment_id, db_session,
            plan_status=InstallmentPlanStatus.ACTIVE,
        )
    )
    plan_id, tranche_id = plan.id, paid_tranche.id
    sibling_id, purchase_id = sibling.id, purchase.id

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback funded a tranche"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["purchases_reversed"] == 1
    assert len(body["tranches_unwound"]) == 1
    assert body["tranches_unwound"][0]["plan_outcome"] == "defaulted"
    assert body["tranches_unwound"][0]["cancelled_count"] == 1

    db_session.expire_all()
    purchase_after = (
        await db_session.execute(
            sa_select(Purchase).where(Purchase.id == purchase_id)
        )
    ).scalar_one()
    tranche_after = (
        await db_session.execute(
            sa_select(InstallmentTranche).where(
                InstallmentTranche.id == tranche_id
            )
        )
    ).scalar_one()
    sibling_after = (
        await db_session.execute(
            sa_select(InstallmentTranche).where(
                InstallmentTranche.id == sibling_id
            )
        )
    ).scalar_one()
    plan_after = (
        await db_session.execute(
            sa_select(InstallmentPlan).where(InstallmentPlan.id == plan_id)
        )
    ).scalar_one()

    assert purchase_after.status == PStatus.REVERSED
    assert tranche_after.status == InstallmentTrancheStatus.REVERSED
    assert sibling_after.status == InstallmentTrancheStatus.CANCELLED
    assert plan_after.status == InstallmentPlanStatus.DEFAULTED
    assert plan_after.defaulted_at is not None


@pytest.mark.asyncio
async def test_reverse_payment_flags_completed_plan_is07(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tranche-unwind on a COMPLETED plan (boss-locked p.4): the plan
    is NOT unwound -- it stays COMPLETED, the tranche flips to
    REVERSED, and semaphore IS-07 goes up by exactly one so the case
    cannot be quietly forgotten. Delta-assert (shared dev DB)."""
    from sqlalchemy import select as sa_select

    from app.modules.installments.constants import (
        InstallmentPlanStatus,
        InstallmentTrancheStatus,
    )
    from app.modules.installments.models import (
        InstallmentPlan,
        InstallmentTranche,
    )

    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    plan, paid_tranche, _, _ = await _build_plan_with_paid_tranche(
        user_id, payment_id, db_session,
        plan_status=InstallmentPlanStatus.COMPLETED,
    )
    plan_id, tranche_id = plan.id, paid_tranche.id

    # IS-07 baseline before the reversal.
    resp0 = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(admin_token),
    )
    assert resp0.status_code == 200
    is07 = next(r for r in resp0.json()["results"] if r["name"] == "IS-07")
    baseline = is07["details"]["completed_plans_with_reversed_funding"]

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback after completion"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["tranches_unwound"][0]["plan_outcome"] == (
        "completed_flagged"
    )

    db_session.expire_all()
    plan_after = (
        await db_session.execute(
            sa_select(InstallmentPlan).where(InstallmentPlan.id == plan_id)
        )
    ).scalar_one()
    tranche_after = (
        await db_session.execute(
            sa_select(InstallmentTranche).where(
                InstallmentTranche.id == tranche_id
            )
        )
    ).scalar_one()
    assert plan_after.status == InstallmentPlanStatus.COMPLETED
    assert tranche_after.status == InstallmentTrancheStatus.REVERSED

    resp1 = await client.get(
        "/api/v1/staff/consistency", headers=auth_headers(admin_token),
    )
    is07_after = next(
        r for r in resp1.json()["results"] if r["name"] == "IS-07"
    )
    assert (
        is07_after["details"]["completed_plans_with_reversed_funding"]
        == baseline + 1
    )
    assert is07_after["status"] == "fail"


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
async def test_reverse_payment_emits_notification_to_payer_only(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reversal -> payment.reversed on the outbox, targeting ONLY
    payment.user_id (the payer) -- not the agent whose commission was
    clawed back in the same reversal. Also asserts the body's dollar
    amount is payment.amount_cents, not total_reversed_cents (which
    would double-count the agent's clawed-back commission -- a
    different user's money)."""
    from uuid import uuid4 as _uuid4

    from app.modules.ledgers.service import record_passive_ledger

    monkeypatch.setattr(settings, "comms_api_url", "http://comms.test")
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    agent_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    # Frozen-funded commission credit on the SAME payment (shaped like
    # ReferralProcessor output), so affected_user_ids includes agent_id
    # too -- this is exactly the scenario the recipient-scope judgment
    # call is about.
    await record_passive_ledger(
        db_session,
        user_id=agent_id,
        amount_cents=500,
        status=LedgerStatus.FROZEN,
        reason=f"commission:l1:{agent_id}:{_uuid4()}",
        frozen_until=datetime.now(UTC) + timedelta(hours=24),
        origin_payment_id=payment_id,
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["total_reversed_cents"] == 10050 + 500

    events = await _notification_events(db_session)
    matches = [
        e for e in events
        if e.payload.get("idempotency_key") == f"payment-reversed:{payment_id}"
    ]
    assert len(matches) == 1
    payload = matches[0].payload
    assert payload["type"] == "payment.reversed"
    assert payload["target_type"] == "user"
    assert payload["target_value"] == str(user_id)
    # payment.amount_cents (100.50), NOT total_reversed_cents (105.50).
    assert "100.50" in payload["body"]
    assert "chargeback" in payload["body"]

    # No notification was emitted targeting the agent for this reversal.
    agent_matches = [
        e for e in events if e.payload.get("target_value") == str(agent_id)
    ]
    assert agent_matches == []


@pytest.mark.asyncio
async def test_reverse_without_comms_emits_no_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No comms address -> no outbox row."""
    monkeypatch.setattr(settings, "comms_api_url", "")
    admin_token = await _admin_token(client, db_session)
    user_id = await _create_investor(client)
    payment_id = await _create_frozen_payment_with_ledger(user_id, db_session)

    resp = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "chargeback"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200

    events = await _notification_events(db_session)
    matches = [
        e for e in events
        if e.payload.get("idempotency_key") == f"payment-reversed:{payment_id}"
    ]
    assert matches == []
