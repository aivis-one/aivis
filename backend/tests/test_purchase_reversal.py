# =============================================================================
# CBSHOME Backend -- Purchase Reversal Tests (R-2.2 Blocks B + C)
# =============================================================================
#
# Tests cover:
#   1: Manual reverse of a CONFIRMED-funded purchase -> 200: investor
#      refunded paid_cents, agent commission clawed back, Purchase
#      REVERSED, units leave pool consumption, all entry pairs REVERSED
#      and sum to 0
#   2: Repeat reversal -> 400 (status guard)
#   3: Without payment_review permission -> 403
#   4: Non-existent purchase -> 404
#   5: Installment-tranche purchase -> 400 (out of scope by design)
#   6: Manual purchase reversal, THEN reversal of the funding frozen
#      payment -> deposit unwinds alone, purchase entries not captured
#      twice (purchases_reversed == 0 on the payment side)
#   7: S-02 / S-03 delta-neutrality: semaphore results (pass/fail +
#      counts deltas) are unchanged by a reversal -- the ":reversal"
#      mirrors are excluded from both formulas (Block C). Shared dev
#      DB forbids asserting a global green, so the test asserts the
#      reversal contributes zero drift instead.
#
# SEEDING SHAPE:
#   Purchases are seeded directly (Purchase row + ledger entries in
#   exactly the shape purchases/engine.write_transactions produces)
#   rather than driving the HTTP purchase flow -- the reversal capture
#   works by reason, and the seeded reasons replicate the engine's
#   formats verbatim ("purchase:{id}", "commission:l1:{agent}:{id}").
#
# Email prefix: random via register_user -- no fixture cleanup needed.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.ledgers.service import (
    get_active_balance,
    get_passive_balance,
    record_active_ledger,
    record_passive_ledger,
)
from app.modules.payments.constants import PaymentStatus, PaymentType
from app.modules.payments.models import Payment
from app.modules.pools.service import get_pool_consumed
from app.modules.products.models import Product
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.staff.consistency.service import s_02, s_03
from tests.helpers import auth_headers, create_admin_user, register_user


async def _admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(client, db_session)
    return token


async def _investor(client: AsyncClient) -> UUID:
    """Helper: register a user and return their UUID."""
    data = await register_user(client)
    return UUID(data["user"]["id"])


async def _seeded_product(db_session: AsyncSession) -> Product:
    """Any storefront-seeded product (company link for purchases)."""
    product = (
        await db_session.execute(select(Product).limit(1))
    ).scalar_one_or_none()
    assert product is not None, "storefront seed must run before tests"
    return product


async def _seed_purchase_graph(
    db_session: AsyncSession,
    *,
    investor_id: UUID,
    agent_id: UUID | None = None,
    paid_cents: int = 10050,
    units: int = 1,
    ledger_status: str = LedgerStatus.CONFIRMED,
    origin_payment_id: UUID | None = None,
    legal_basis: str = PurchaseLegalBasis.SALE,
    fund_investor: bool = True,
) -> Purchase:
    """Seed a Purchase + its money graph in engine-verbatim shape.

    Writes: optional funding deposit (+2x paid), investor debit
    "purchase:{id}", platform-substitute passive credit is skipped
    (platform user id is irrelevant to the assertions -- the credit is
    seeded onto the AGENT when agent_id is given, in the commission
    reason shape, which is the clawback path under test).
    """
    frozen_until = (
        datetime.now(UTC) + timedelta(hours=24)
        if ledger_status == LedgerStatus.FROZEN
        else None
    )

    product = await _seeded_product(db_session)

    if fund_investor:
        await record_active_ledger(
            db_session,
            user_id=investor_id,
            amount_cents=paid_cents * 2,
            status=LedgerStatus.CONFIRMED,
            reason=f"deposit:crypto:0x_pr_{uuid4().hex[:8]}",
        )

    purchase = Purchase(
        investor_id=investor_id,
        product_id=product.id,
        company_id=product.company_id,
        legal_basis=legal_basis,
        units=units,
        paid_cents=paid_cents,
        price_per_unit_cents=paid_cents // max(units, 1),
        status=PurchaseStatus.ACTIVE,
    )
    db_session.add(purchase)
    await db_session.flush()

    await record_active_ledger(
        db_session,
        user_id=investor_id,
        amount_cents=-paid_cents,
        status=ledger_status,
        reason=f"purchase:{purchase.id}",
        frozen_until=frozen_until,
        origin_payment_id=origin_payment_id,
    )

    if agent_id is not None:
        await record_passive_ledger(
            db_session,
            user_id=agent_id,
            amount_cents=500,
            status=ledger_status,
            reason=f"commission:l1:{agent_id}:{purchase.id}",
            frozen_until=frozen_until,
            origin_payment_id=origin_payment_id,
        )

    await db_session.commit()
    return purchase


# ---------------------------------------------------------------------------
# 1. Happy path: refund + clawback + asset + pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_reverse_confirmed_purchase(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Confirmed-funded purchase -> manual reverse: investor refunded,
    agent clawed back, Purchase REVERSED, units leave the pool, every
    captured pair is REVERSED and sums to zero."""
    admin_token = await _admin_token(client, db_session)
    investor_id = await _investor(client)
    agent_id = await _investor(client)

    purchase = await _seed_purchase_graph(
        db_session, investor_id=investor_id, agent_id=agent_id
    )
    purchase_id = purchase.id
    company_id = purchase.company_id
    units = purchase.units

    # Baselines (shared dev DB -- assert deltas, not absolutes).
    before = await get_active_balance(db_session, investor_id)
    assert before["confirmed"] == 10050  # 2x deposit - paid
    consumed_before = await get_pool_consumed(company_id, db_session)

    resp = await client.post(
        f"/api/v1/staff/purchases/{purchase_id}/reverse",
        json={"reason": "manual chargeback"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # |investor -10050| + |agent +500|.
    assert body["total_reversed_cents"] == 10550
    assert body["active_entries_reversed"] == 1
    assert body["passive_entries_reversed"] == 1
    assert body["units_returned"] == units

    db_session.expire_all()

    # Refund: the debit left the spendable balance.
    after = await get_active_balance(db_session, investor_id)
    assert after["confirmed"] == 20100

    # Clawback: agent commission gone.
    agent_balance = await get_passive_balance(db_session, agent_id)
    assert agent_balance["frozen"] == 0
    assert agent_balance["confirmed"] == 0

    # Asset: Purchase REVERSED, pool consumption dropped.
    p = (await db_session.execute(
        select(Purchase).where(Purchase.id == purchase_id)
    )).scalar_one()
    assert p.status == PurchaseStatus.REVERSED
    consumed_after = await get_pool_consumed(company_id, db_session)
    assert consumed_after == consumed_before - units

    # Invariants: pairs REVERSED, sum 0 (active + passive).
    pid = str(purchase_id)
    a_entries = (await db_session.execute(
        select(ActiveLedger).where(ActiveLedger.reason.like(f"%{pid}%"))
    )).scalars().all()
    p_entries = (await db_session.execute(
        select(PassiveLedger).where(PassiveLedger.reason.like(f"%{pid}%"))
    )).scalars().all()
    assert len(a_entries) == 2 and len(p_entries) == 2
    assert all(
        e.status == LedgerStatus.REVERSED for e in [*a_entries, *p_entries]
    )
    assert sum(e.amount_cents for e in a_entries) == 0
    assert sum(e.amount_cents for e in p_entries) == 0


# ---------------------------------------------------------------------------
# 2-5. Guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_reverse_repeat_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Second reversal of the same purchase -> 400 (ACTIVE guard)."""
    admin_token = await _admin_token(client, db_session)
    investor_id = await _investor(client)
    purchase = await _seed_purchase_graph(
        db_session, investor_id=investor_id
    )

    resp1 = await client.post(
        f"/api/v1/staff/purchases/{purchase.id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        f"/api/v1/staff/purchases/{purchase.id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_manual_reverse_without_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Without payment_review permission -> 403."""
    admin_token = await _admin_token(client, db_session)

    noperm_email = f"noperm_pr_{uuid4().hex[:12]}@example.com"
    staff_data = await register_user(client, email=noperm_email)
    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": staff_data["user"]["id"]},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    profile_id = resp.json()["id"]

    await client.patch(
        f"/api/v1/staff/users/{profile_id}/permissions",
        json={"payment_review": False},
        headers=auth_headers(admin_token),
    )

    from tests.helpers import login_user
    login_data = await login_user(client, email=noperm_email)
    restricted_token = login_data["session_token"]

    resp2 = await client.post(
        f"/api/v1/staff/purchases/{uuid4()}/reverse",
        json={},
        headers=auth_headers(restricted_token),
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_manual_reverse_nonexistent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Non-existent purchase -> 404."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        f"/api/v1/staff/purchases/{uuid4()}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_manual_reverse_tranche_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Installment-tranche purchase -> 400 (out of R-2.2 scope)."""
    admin_token = await _admin_token(client, db_session)
    investor_id = await _investor(client)
    purchase = await _seed_purchase_graph(
        db_session,
        investor_id=investor_id,
        legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE,
        fund_investor=False,
    )

    resp = await client.post(
        f"/api/v1/staff/purchases/{purchase.id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 6. Manual purchase reversal, then payment reversal -- no double unwind
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_then_payment_reversal_no_double_unwind(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Frozen-funded purchase reversed manually, THEN the funding
    payment is reversed: the payment side unwinds the deposit alone --
    the purchase entries are already REVERSED and the status filter
    skips them (purchases_reversed == 0, exactly 1 active entry)."""
    admin_token = await _admin_token(client, db_session)
    investor_id = await _investor(client)

    # Frozen payment + deposit ledger (engine shape).
    frozen_until = datetime.now(UTC) + timedelta(hours=24)
    payment = Payment(
        user_id=investor_id,
        amount_cents=10050,
        currency="USD",
        payment_type=PaymentType.CRYPTO,
        provider="crypto_usdt_trc20",
        status=PaymentStatus.FROZEN,
        frozen_until=frozen_until,
        provider_data={"tx_hash": f"0x_pr2_{uuid4().hex[:8]}"},
    )
    db_session.add(payment)
    await db_session.flush()
    payment_id = payment.id

    await record_active_ledger(
        db_session,
        user_id=investor_id,
        amount_cents=10050,
        status=LedgerStatus.FROZEN,
        reason=f"deposit:crypto:0x_pr2_{uuid4().hex[:8]}",
        frozen_until=frozen_until,
        origin_payment_id=payment_id,
    )
    await db_session.commit()

    # Frozen-funded purchase inheriting the payment's origin id.
    purchase = await _seed_purchase_graph(
        db_session,
        investor_id=investor_id,
        ledger_status=LedgerStatus.FROZEN,
        origin_payment_id=payment_id,
        fund_investor=False,
    )

    # 1) Manual purchase reversal.
    resp1 = await client.post(
        f"/api/v1/staff/purchases/{purchase.id}/reverse",
        json={"reason": "manual first"},
        headers=auth_headers(admin_token),
    )
    assert resp1.status_code == 200
    assert resp1.json()["total_reversed_cents"] == 10050

    # 2) Payment reversal: captures ONLY the deposit -- the purchase
    # rows are already REVERSED.
    resp2 = await client.post(
        f"/api/v1/staff/payments/{payment_id}/reverse",
        json={"reason": "payment second"},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["active_entries_reversed"] == 1
    assert body["total_reversed_cents"] == 10050
    assert body["purchases_reversed"] == 0

    # Net: deposit gone, refund gone with it -- balance exactly 0.
    db_session.expire_all()
    balance = await get_active_balance(db_session, investor_id)
    assert balance["frozen"] == 0
    assert balance["confirmed"] == 0


# ---------------------------------------------------------------------------
# 7. S-02 / S-03 delta-neutrality (Block C)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s02_s03_delta_neutral_under_reversal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A reversal contributes ZERO drift to S-02 and S-03.

    Shared dev DB forbids asserting a global pass (historical state is
    unknowable), so the test snapshots both semaphores after seeding a
    purchase and asserts the snapshots are IDENTICAL after reversing
    it: the Purchase row and its original debit stay in both formulas,
    the ":reversal" mirrors are excluded (Block C). Pre-fix, S-02
    ledger_count grew by 1 and S-03 debit_total collapsed to 0 here.
    """
    admin_token = await _admin_token(client, db_session)
    investor_id = await _investor(client)
    purchase = await _seed_purchase_graph(
        db_session, investor_id=investor_id
    )

    before_02 = (await s_02(db_session)).details
    before_03 = (await s_03(db_session)).details

    resp = await client.post(
        f"/api/v1/staff/purchases/{purchase.id}/reverse",
        json={},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200

    after_02 = (await s_02(db_session)).details
    after_03 = (await s_03(db_session)).details

    assert after_02 == before_02, (
        "reversal must not drift S-02 counts (mirrors excluded)"
    )
    assert after_03 == before_03, (
        "reversal must not drift S-03 sums (mirrors excluded)"
    )
