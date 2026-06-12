# =============================================================================
# CBSHOME Backend -- Pool Capacity Tests (R51)
# =============================================================================
#
# Tests cover:
#   1: get_pool_reserved lifecycle -- ACTIVE plan reserves total_units,
#      a PAID tranche reduces the reservation (its units became a
#      Purchase), DEFAULTED plan releases the remainder (zero code in
#      default path -- status-driven formula)
#   2: get_pool_remaining subtracts both consumption and reservation
#   3: paid tranche is net-zero -- reservation converts into
#      consumption 1:1, remaining unchanged
#   4: create_plan rejects a plan over remaining capacity (400),
#      first plan within capacity succeeds (the R51 reservation guard)
#   5: instant purchase is rejected when ACTIVE plans reserved the
#      remainder ("Sold out" fires at step 4, before any money moves)
#
# FIXTURE STRATEGY:
#   Shared dev DB forbids absolute assertions against seeded pools, so
#   every test builds its OWN mini-company (owner user via API +
#   CompanyProfile + OptionPool with a small total_options + Product
#   [+ ProductInstallment template]) -- full control of the remainder,
#   absolute asserts are safe. Row shapes mirror seed_test_accounts.py.
#
# P-01: services never commit -- tests commit after service calls.
# =============================================================================

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.models import CompanyProfile
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.installments.service import create_plan
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import record_active_ledger
from app.modules.pools.models import OptionPool
from app.modules.pools.service import get_pool_remaining, get_pool_reserved
from app.modules.products.models import Product, ProductInstallment, ProductStatus
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.purchases.service import execute_purchase
from app.modules.users.models import KYCStatus, User
from tests.helpers import register_user

# Mini-company economics: 1000 cents/unit, packages of 4 units.
_PRICE = 1000
_PACKAGE = 4


async def _approved_user(
    client: AsyncClient, db_session: AsyncSession
) -> User:
    """Register a user via API and flip kyc_status to APPROVED."""
    data = await register_user(client)
    user_id = UUID(data["user"]["id"])
    user = (await db_session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one()
    user.kyc_status = KYCStatus.APPROVED
    await db_session.commit()
    return user


async def _mini_company(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    total_options: int,
    with_installment: bool = False,
) -> tuple[CompanyProfile, OptionPool, Product, ProductInstallment | None]:
    """Build a private company + pool + product (+ template).

    Row shapes mirror seed_test_accounts.py so the fixtures stay in
    lockstep with the real seeding path.
    """
    owner_data = await register_user(client)
    owner_id = UUID(owner_data["user"]["id"])
    tag = uuid4().hex[:8]

    company = CompanyProfile(
        user_id=owner_id,
        name=f"PoolCap Test Co {tag}",
        description="R51 pool-capacity test fixture.",
        logo_url=None,
        cover_url=None,
        promo_video_url=None,
        presentation_url=None,
        price_per_unit_cents=_PRICE,
        total_supply=total_options,
        shares_per_option=1,
        # NOT NULL in company_profiles; shape mirrors the seed script.
        distribution_config={
            "company_pct": 0.80,
            "agent_levels": [0.10, 0.05, 0.05],
        },
        status=CompanyStatus.ACTIVE,
    )
    db_session.add(company)
    await db_session.flush()

    pool = OptionPool(
        company_id=company.id,
        equity_percent=Decimal("100.0000"),
        total_options=total_options,
        status="active",
    )
    db_session.add(pool)
    await db_session.flush()

    product = Product(
        company_id=company.id,
        pool_id=pool.id,
        name=f"PoolCap Product {tag}",
        description="R51 test product.",
        package_size=_PACKAGE,
        price_per_unit_cents=_PRICE,
        purchase_config={},
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    template: ProductInstallment | None = None
    if with_installment:
        total = _PRICE * _PACKAGE
        per = total // 3
        template = ProductInstallment(
            product_id=product.id,
            name=f"PoolCap Plan {tag}",
            plan_config={
                "tranches": [
                    {"amount_cents": per, "units_percent": 33},
                    {"amount_cents": per, "units_percent": 33},
                    {"amount_cents": total - per * 2, "units_percent": 34},
                ],
                "bonus_units": 0,
                "agent_bonus_units": 0,
            },
        )
        db_session.add(template)
        await db_session.flush()

    await db_session.commit()
    return company, pool, product, template


def _plan_row(
    company: CompanyProfile,
    product: Product,
    investor_id: UUID,
    template_id: UUID,
    *,
    total_units: int,
    status: str = InstallmentPlanStatus.ACTIVE,
) -> InstallmentPlan:
    """Bare InstallmentPlan row for formula-level tests."""
    return InstallmentPlan(
        investor_id=investor_id,
        product_id=product.id,
        product_installment_id=template_id,
        company_id=company.id,
        plan_config_snapshot={"tranches": []},
        total_price_cents=total_units * _PRICE,
        total_units=total_units,
        price_per_unit_cents=_PRICE,
        referral_link_id=None,
        agent_id=None,
        status=status,
    )


# ---------------------------------------------------------------------------
# 1-3. Reservation formula (rows only, absolute asserts on own company)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_reserved_lifecycle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ACTIVE plan reserves total_units; PAID tranche reduces it;
    DEFAULTED plan releases the remainder -- all via status alone."""
    company, _pool, product, template = await _mini_company(
        client, db_session, total_options=10, with_installment=True
    )
    investor_data = await register_user(client)
    investor_id = UUID(investor_data["user"]["id"])

    assert await get_pool_reserved(company.id, db_session) == 0

    plan = _plan_row(company, product, investor_id, template.id, total_units=6)
    db_session.add(plan)
    await db_session.commit()

    assert await get_pool_reserved(company.id, db_session) == 6

    # Pay one tranche worth 2 units -- reservation drops to 4 (the
    # paid units now live as a Purchase, counted by consumed).
    tranche = InstallmentTranche(
        plan_id=plan.id,
        number=1,
        due_date=date.today(),
        amount_cents=2 * _PRICE,
        units_unlocked=2,
        status=InstallmentTrancheStatus.PAID,
        paid_at=datetime.now(UTC),
    )
    db_session.add(tranche)
    await db_session.commit()

    assert await get_pool_reserved(company.id, db_session) == 4

    # Default the plan: remainder released, zero code in default path.
    plan.status = InstallmentPlanStatus.DEFAULTED
    await db_session.commit()

    assert await get_pool_reserved(company.id, db_session) == 0


@pytest.mark.asyncio
async def test_pool_remaining_subtracts_reservation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """remaining = total - consumed - reserved."""
    company, pool, product, template = await _mini_company(
        client, db_session, total_options=10, with_installment=True
    )
    investor_data = await register_user(client)
    investor_id = UUID(investor_data["user"]["id"])

    assert await get_pool_remaining(pool, db_session) == 10

    plan = _plan_row(company, product, investor_id, template.id, total_units=6)
    db_session.add(plan)

    purchase = Purchase(
        investor_id=investor_id,
        product_id=product.id,
        company_id=company.id,
        legal_basis=PurchaseLegalBasis.SALE,
        units=2,
        paid_cents=2 * _PRICE,
        price_per_unit_cents=_PRICE,
        status=PurchaseStatus.ACTIVE,
    )
    db_session.add(purchase)
    await db_session.commit()

    # 10 - consumed(2) - reserved(6) = 2.
    assert await get_pool_remaining(pool, db_session) == 2


@pytest.mark.asyncio
async def test_paid_tranche_is_net_zero_for_remaining(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Paying a tranche converts reservation into consumption 1:1."""
    company, pool, product, template = await _mini_company(
        client, db_session, total_options=10, with_installment=True
    )
    investor_data = await register_user(client)
    investor_id = UUID(investor_data["user"]["id"])

    plan = _plan_row(company, product, investor_id, template.id, total_units=6)
    db_session.add(plan)
    await db_session.commit()

    before = await get_pool_remaining(pool, db_session)
    assert before == 4  # 10 - reserved(6)

    # Simulate a paid tranche exactly as pay_tranche leaves the DB:
    # PAID tranche (2 units) + the Purchase the engine wrote for it.
    tranche = InstallmentTranche(
        plan_id=plan.id,
        number=1,
        due_date=date.today(),
        amount_cents=2 * _PRICE,
        units_unlocked=2,
        status=InstallmentTrancheStatus.PAID,
        paid_at=datetime.now(UTC),
    )
    db_session.add(tranche)
    db_session.add(Purchase(
        investor_id=investor_id,
        product_id=product.id,
        company_id=company.id,
        legal_basis=PurchaseLegalBasis.INSTALLMENT_TRANCHE,
        units=2,
        paid_cents=2 * _PRICE,
        price_per_unit_cents=_PRICE,
        status=PurchaseStatus.ACTIVE,
    ))
    await db_session.commit()

    # consumed +2, reserved -2 -> remaining unchanged.
    assert await get_pool_remaining(pool, db_session) == before


# ---------------------------------------------------------------------------
# 4-5. Guards through the real services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_plan_rejects_over_capacity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """First plan (4 of 6 units) fits; second (4 > remaining 2) -> 400."""
    company, _pool, product, template = await _mini_company(
        client, db_session, total_options=6, with_installment=True
    )
    investor = await _approved_user(client, db_session)

    # Fund the balance pre-check (first tranche).
    await record_active_ledger(
        db_session,
        user_id=investor.id,
        amount_cents=20_000,
        status=LedgerStatus.CONFIRMED,
        reason=f"deposit:crypto:0x_poolcap_{uuid4().hex[:8]}",
    )
    await db_session.commit()

    plan = await create_plan(
        product_id=product.id,
        product_installment_id=template.id,
        investor=investor,
        session=db_session,
        referral_link_id=None,
    )
    await db_session.commit()
    assert plan.total_units == _PACKAGE

    # Remaining is now 2 -- a second 4-unit plan must be rejected.
    with pytest.raises(BadRequestError) as exc:
        await create_plan(
            product_id=product.id,
            product_installment_id=template.id,
            investor=investor,
            session=db_session,
            referral_link_id=None,
        )
    await db_session.rollback()
    assert "pool capacity" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_instant_purchase_rejected_when_reserved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """ACTIVE plans hold their units against instant buyers: with 2 of
    6 units left after a 4-unit plan, a 4-unit purchase -> Sold out.
    Fires at step 4, before any money moves (buyer is unfunded)."""
    company, _pool, product, template = await _mini_company(
        client, db_session, total_options=6, with_installment=True
    )
    plan_investor_data = await register_user(client)
    plan_investor_id = UUID(plan_investor_data["user"]["id"])

    plan = _plan_row(company, product, plan_investor_id, template.id, total_units=4)
    db_session.add(plan)
    await db_session.commit()

    buyer = await _approved_user(client, db_session)

    with pytest.raises(BadRequestError) as exc:
        await execute_purchase(
            product_id=product.id,
            investor=buyer,
            session=db_session,
            referral_link_id=None,
        )
    await db_session.rollback()
    assert "sold out" in str(exc.value).lower()
