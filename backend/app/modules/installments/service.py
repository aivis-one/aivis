# =============================================================================
# CBSHOME Backend -- Installment Service (Sprint 6.2, fix #35, updated 6.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_plan()        -- create installment plan + expand tranches
#   pay_tranche()        -- pay a single tranche via engine.execute()
#   complete_plan()      -- award bonuses, set completed
#   default_plan()       -- set defaulted, cancel remaining tranches
#   get_investor_plans() -- list plans for GET /installments/me
#   get_plan_detail()    -- plan + tranches for GET /installments/{id}
#
# ARCHITECTURE:
#   Tranche payment delegates to purchases/engine.execute() with a
#   PurchaseContext built from plan snapshot + current distribution_config.
#   Product/Company are loaded without status checks -- installment plans
#   survive product archival.
#
#   Completion bonuses are written via engine.write_transactions() with
#   manually-built Transaction objects (fixed bonus, not condition-based).
#
# Fix #35: catch InsufficientBalanceError by type, not string match.
#
# Sprint 6.4: record_transaction() calls for tranche_paid, completed,
#   defaulted events.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

from datetime import date, datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.constants import LedgerReason
from app.core.exceptions import BadRequestError, InsufficientBalanceError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.installments.constants import (
    InstallmentPlanStatus,
    InstallmentTrancheStatus,
    validate_plan_status_transition,
    validate_tranche_status_transition,
)
from app.modules.installments.models import InstallmentPlan, InstallmentTranche
from app.modules.installments.scheduler import calculate_due_date
from app.modules.processors.base import LedgerEntry, PurchaseContext, Transaction
from app.modules.products.models import Product, ProductInstallment
from app.modules.purchases import engine
from app.modules.referrals.service import create_attribution, get_agent_chain
from app.modules.purchases.service import (
    compute_frozen_context,
    get_investor_portfolio_cents,
    get_platform_user,
)
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction
from app.modules.users.models import KYCStatus, User

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Plan creation
# ---------------------------------------------------------------------------


async def create_plan(
    product_id: UUID,
    product_installment_id: UUID,
    investor: User,
    session: AsyncSession,
    *,
    referral_link_id: UUID | None = None,
) -> InstallmentPlan:
    """Create an installment plan from a ProductInstallment template.

    Snapshots plan_config, expands tranches, validates first tranche
    affordability. Does NOT pay the first tranche -- daemon handles it.

    Args:
        product_id: Product being purchased.
        product_installment_id: Template to snapshot.
        investor: Authenticated investor.
        session: Active DB session. Caller manages commit (P-01).
        referral_link_id: Optional referral link (Sprint 7.2 stub).

    Returns:
        Created InstallmentPlan with tranches.

    Raises:
        NotFoundError: Product or template not found.
        BadRequestError: Template doesn't belong to product, insufficient
            balance for first tranche, product not active.
    """
    now = datetime.now(UTC)
    today = now.date()

    # -- KYC guard (TD-038) --
    if investor.kyc_status != KYCStatus.APPROVED:
        raise BadRequestError(
            "KYC verification required before installment purchase"
        )

    # -- 1. Load Product (must be active for new plans) --
    product = await _load_product_active(product_id, session)

    # -- 2. Load Company (must be active for new plans) --
    company = await _load_company_active(product.company_id, session)

    # -- 3. Load ProductInstallment template --
    template = await _load_template(product_installment_id, session)

    if template.product_id != product.id:
        raise BadRequestError(
            "Installment template does not belong to this product"
        )

    # -- 4. Snapshot plan_config --
    snapshot = dict(template.plan_config)
    tranches_config = snapshot["tranches"]
    bonus_units = snapshot.get("bonus_units", 0)
    agent_bonus_units = snapshot.get("agent_bonus_units", 0)

    total_price_cents = sum(t["amount_cents"] for t in tranches_config)
    total_units = product.units

    # -- 5. Create InstallmentPlan --
    plan = InstallmentPlan(
        investor_id=investor.id,
        product_id=product.id,
        product_installment_id=template.id,
        company_id=company.id,
        plan_config_snapshot=snapshot,
        total_price_cents=total_price_cents,
        total_units=total_units,
        price_per_unit_cents=product.price_per_unit_cents,
        referral_link_id=referral_link_id,
        agent_id=None,  # Sprint 7.x stub
        status=InstallmentPlanStatus.ACTIVE,
    )
    session.add(plan)
    await session.flush()
    await session.refresh(plan)

    # -- 6. Expand tranches from snapshot --
    for i, tranche_cfg in enumerate(tranches_config):
        number = i + 1
        if number == 1:
            due = today
        else:
            due = calculate_due_date(today, number - 1)

        units_unlocked = tranche_cfg["units_percent"] * total_units // 100

        tranche = InstallmentTranche(
            plan_id=plan.id,
            number=number,
            due_date=due,
            amount_cents=tranche_cfg["amount_cents"],
            units_unlocked=units_unlocked,
            status=InstallmentTrancheStatus.SCHEDULED,
        )
        session.add(tranche)

    await session.flush()

    # -- 7. Audit --
    await record_audit(
        session=session,
        event="installment.plan_created",
        actor_id=investor.id,
        actor_type="user",
        target_type="installment_plan",
        target_id=plan.id,
        data={
            "product_id": str(product.id),
            "template_id": str(template.id),
            "total_price_cents": total_price_cents,
            "total_units": total_units,
            "tranche_count": len(tranches_config),
        },
    )

    logger.info(
        "installment_plan_created",
        plan_id=str(plan.id),
        investor_id=str(investor.id),
        product_id=str(product.id),
        tranche_count=len(tranches_config),
    )

    return plan


# ---------------------------------------------------------------------------
# Tranche payment
# ---------------------------------------------------------------------------


async def pay_tranche(
    tranche: InstallmentTranche,
    plan: InstallmentPlan,
    session: AsyncSession,
) -> bool:
    """Attempt to pay a single tranche via engine.execute().

    Called by daemon for scheduled/overdue tranches with due_date <= today.

    If investor has sufficient balance, pays the tranche:
      - Runs PurchaseProcessor via engine (distribution to company)
      - Sets tranche status=paid, paid_at, purchase_id
      - If last tranche -> calls complete_plan()

    If insufficient balance, sets tranche to overdue (or keeps overdue).

    Args:
        tranche: InstallmentTranche to pay.
        plan: Parent InstallmentPlan (must be active).
        session: Active DB session.

    Returns:
        True if tranche was paid, False if insufficient balance (overdue).
    """
    now = datetime.now(UTC)

    # -- 1. Load Product + Company (no status check) --
    product = await _load_product_any(plan.product_id, session)
    company = await _load_company_any(plan.company_id, session)
    company_user = await _load_user(company.user_id, session)
    platform_user = await get_platform_user(session)

    # -- 2. Compute frozen context --
    frozen_until, origin_payment_id = await compute_frozen_context(
        session, plan.investor_id
    )

    # -- 3. Resolve distribution_config --
    dist_config = _resolve_distribution_config(product, company)

    # -- 4. Build PurchaseContext for this tranche --
    context = PurchaseContext(
        investor_id=plan.investor_id,
        product_id=plan.product_id,
        company_id=plan.company_id,
        company_user_id=company.user_id,
        platform_user_id=platform_user.id,
        amount_cents=tranche.amount_cents,
        units=tranche.units_unlocked,
        price_per_unit_cents=plan.price_per_unit_cents,
        distribution_config=dist_config,
        purchase_config_bonuses=[],  # No per-tranche bonuses
        origin_payment_id=origin_payment_id,
        frozen_until=frozen_until,
        agent_chain=await get_agent_chain(
            plan.investor_id,
            session,
            max_depth=len(dist_config.get("agent_levels", [])),
        ),  # Sprint 7.x stub
        triggered_at=now,
    )

    # -- 5. Execute via engine (fix #35: catch by type, not string) --
    try:
        purchases = await engine.execute(context, session)
    except InsufficientBalanceError:
        # Mark as overdue (if not already).
        if tranche.status == InstallmentTrancheStatus.SCHEDULED:
            validate_tranche_status_transition(
                tranche.status, InstallmentTrancheStatus.OVERDUE
            )
            tranche.status = InstallmentTrancheStatus.OVERDUE
            await session.flush()

            await record_audit(
                session=session,
                event="installment.tranche_overdue",
                actor_id=plan.investor_id,
                actor_type="system",
                target_type="installment_tranche",
                target_id=tranche.id,
                data={
                    "plan_id": str(plan.id),
                    "tranche_number": tranche.number,
                    "amount_cents": tranche.amount_cents,
                },
            )

        logger.info(
            "installment_tranche_overdue",
            tranche_id=str(tranche.id),
            plan_id=str(plan.id),
            amount_cents=tranche.amount_cents,
        )
        return False

    # -- 6. Update tranche --
    # Engine returns [sale_purchase]. Take the first (sale) purchase.
    sale_purchase = next(
        p for p in purchases if p.legal_basis != "gift"
    )

    validate_tranche_status_transition(
        tranche.status, InstallmentTrancheStatus.PAID
    )
    tranche.status = InstallmentTrancheStatus.PAID
    tranche.paid_at = now
    tranche.purchase_id = sale_purchase.id
    await session.flush()

    await record_audit(
        session=session,
        event="installment.tranche_paid",
        actor_id=plan.investor_id,
        actor_type="system",
        target_type="installment_tranche",
        target_id=tranche.id,
        data={
            "plan_id": str(plan.id),
            "tranche_number": tranche.number,
            "amount_cents": tranche.amount_cents,
            "purchase_id": str(sale_purchase.id),
        },
    )

    # Sprint 6.4: Transaction log -- installment:tranche_paid.
    await record_transaction(
        session,
        user_id=plan.investor_id,
        type=TransactionType.INSTALLMENT_TRANCHE_PAID,
        amount_cents=-tranche.amount_cents,
        reference_id=plan.id,
        reference_type=ReferenceType.INSTALLMENT_PLAN,
        details={
            "tranche_number": tranche.number,
            "product_id": str(plan.product_id),
            "units_unlocked": tranche.units_unlocked,
            "purchase_id": str(sale_purchase.id),
        },
    )

    # Sprint 7.2: record referral attribution (one per plan, first tranche only).
    if tranche.number == 1:
        await create_attribution(
            sale_purchase.id, plan.referral_link_id, session
        )

    logger.info(
        "installment_tranche_paid",
        tranche_id=str(tranche.id),
        plan_id=str(plan.id),
        tranche_number=tranche.number,
    )

    # -- 7. Check if all tranches paid -> complete --
    all_paid = await _all_tranches_paid(plan.id, session)
    if all_paid:
        await complete_plan(plan, session)

    return True


# ---------------------------------------------------------------------------
# Plan completion
# ---------------------------------------------------------------------------


async def complete_plan(
    plan: InstallmentPlan,
    session: AsyncSession,
) -> None:
    """Complete a plan: set status, award bonuses.

    Called automatically when the last tranche is paid.
    Awards bonus_units to investor and agent_bonus_units to agent L1
    from plan_config_snapshot.

    Args:
        plan: InstallmentPlan to complete.
        session: Active DB session.
    """
    now = datetime.now(UTC)

    validate_plan_status_transition(
        plan.status, InstallmentPlanStatus.COMPLETED
    )
    plan.status = InstallmentPlanStatus.COMPLETED
    plan.completed_at = now
    await session.flush()

    # -- Award completion bonuses --
    snapshot = plan.plan_config_snapshot
    bonus_units = snapshot.get("bonus_units", 0)
    agent_bonus_units = snapshot.get("agent_bonus_units", 0)

    if bonus_units > 0 or (agent_bonus_units > 0 and plan.agent_id is not None):
        await _award_completion_bonuses(
            plan, bonus_units, agent_bonus_units, session
        )

    await record_audit(
        session=session,
        event="installment.plan_completed",
        actor_id=plan.investor_id,
        actor_type="system",
        target_type="installment_plan",
        target_id=plan.id,
        data={
            "bonus_units": bonus_units,
            "agent_bonus_units": agent_bonus_units,
        },
    )

    # Sprint 6.4: Transaction log -- installment:completed.
    await record_transaction(
        session,
        user_id=plan.investor_id,
        type=TransactionType.INSTALLMENT_COMPLETED,
        amount_cents=-plan.total_price_cents,
        reference_id=plan.id,
        reference_type=ReferenceType.INSTALLMENT_PLAN,
        details={
            "product_id": str(plan.product_id),
            "total_units": plan.total_units,
            "bonus_units": bonus_units,
        },
    )

    logger.info(
        "installment_plan_completed",
        plan_id=str(plan.id),
        investor_id=str(plan.investor_id),
    )


# ---------------------------------------------------------------------------
# Plan default
# ---------------------------------------------------------------------------


async def default_plan(
    plan: InstallmentPlan,
    tranche: InstallmentTranche,
    session: AsyncSession,
) -> None:
    """Default a plan: mark tranche defaulted, cancel remaining, set plan defaulted.

    Called by daemon when overdue tranche exceeds INSTALLMENT_DEFAULT_DAYS.
    Investor keeps units from already-paid tranches. No bonus_units awarded.

    Args:
        plan: InstallmentPlan to default.
        tranche: The overdue tranche that triggered the default.
        session: Active DB session.
    """
    now = datetime.now(UTC)

    # -- 1. Set the overdue tranche to defaulted --
    validate_tranche_status_transition(
        tranche.status, InstallmentTrancheStatus.DEFAULTED
    )
    tranche.status = InstallmentTrancheStatus.DEFAULTED
    await session.flush()

    # -- 2. Cancel all remaining scheduled/overdue tranches --
    stmt = (
        select(InstallmentTranche)
        .where(
            InstallmentTranche.plan_id == plan.id,
            InstallmentTranche.id != tranche.id,
            InstallmentTranche.status.in_([
                InstallmentTrancheStatus.SCHEDULED,
                InstallmentTrancheStatus.OVERDUE,
            ]),
        )
    )
    result = await session.execute(stmt)
    remaining = list(result.scalars().all())

    for t in remaining:
        validate_tranche_status_transition(
            t.status, InstallmentTrancheStatus.CANCELLED
        )
        t.status = InstallmentTrancheStatus.CANCELLED

    await session.flush()

    # -- 3. Set plan to defaulted --
    validate_plan_status_transition(
        plan.status, InstallmentPlanStatus.DEFAULTED
    )
    plan.status = InstallmentPlanStatus.DEFAULTED
    plan.defaulted_at = now
    await session.flush()

    await record_audit(
        session=session,
        event="installment.plan_defaulted",
        actor_id=plan.investor_id,
        actor_type="system",
        target_type="installment_plan",
        target_id=plan.id,
        data={
            "trigger_tranche_id": str(tranche.id),
            "trigger_tranche_number": tranche.number,
            "cancelled_count": len(remaining),
        },
    )

    # Sprint 6.4: Transaction log -- installment:defaulted.
    await record_transaction(
        session,
        user_id=plan.investor_id,
        type=TransactionType.INSTALLMENT_DEFAULTED,
        amount_cents=-plan.total_price_cents,
        reference_id=plan.id,
        reference_type=ReferenceType.INSTALLMENT_PLAN,
        details={
            "trigger_tranche_number": tranche.number,
            "cancelled_count": len(remaining),
            "product_id": str(plan.product_id),
        },
    )

    logger.info(
        "installment_plan_defaulted",
        plan_id=str(plan.id),
        investor_id=str(plan.investor_id),
        trigger_tranche=tranche.number,
    )


# ---------------------------------------------------------------------------
# Query helpers (for router)
# ---------------------------------------------------------------------------


async def get_investor_plans(
    investor_id: UUID,
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[InstallmentPlan], int]:
    """List installment plans for an investor.

    Returns (plans, total_count).
    """
    # Count total.
    count_stmt = (
        select(func.count())
        .select_from(InstallmentPlan)
        .where(InstallmentPlan.investor_id == investor_id)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(InstallmentPlan)
        .where(InstallmentPlan.investor_id == investor_id)
        .order_by(InstallmentPlan.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    plans = list(result.scalars().all())

    return plans, total


async def get_plan_detail(
    plan_id: UUID,
    investor_id: UUID,
    session: AsyncSession,
) -> tuple[InstallmentPlan, list[InstallmentTranche]]:
    """Load plan with tranches. Validates ownership.

    Raises:
        NotFoundError: Plan not found or not owned by investor.
    """
    stmt = select(InstallmentPlan).where(InstallmentPlan.id == plan_id)
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()

    if plan is None:
        raise NotFoundError("Installment plan not found")

    if plan.investor_id != investor_id:
        raise NotFoundError("Installment plan not found")

    # Load tranches ordered by number.
    tranche_stmt = (
        select(InstallmentTranche)
        .where(InstallmentTranche.plan_id == plan.id)
        .order_by(InstallmentTranche.number.asc())
    )
    tranche_result = await session.execute(tranche_stmt)
    tranches = list(tranche_result.scalars().all())

    return plan, tranches


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_product_active(
    product_id: UUID, session: AsyncSession
) -> Product:
    """Load product, require active status (for new plan creation)."""
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        raise NotFoundError("Product not found")

    if product.status != "active":
        raise BadRequestError(
            f"Product is not available for purchase (status={product.status})"
        )

    return product


async def _load_company_active(
    company_id: UUID, session: AsyncSession
) -> CompanyProfile:
    """Load company, require active status (for new plan creation)."""
    stmt = select(CompanyProfile).where(CompanyProfile.id == company_id)
    result = await session.execute(stmt)
    company = result.scalar_one_or_none()

    if company is None:
        raise NotFoundError("Company not found")

    if company.status != "active":
        raise BadRequestError(
            f"Company is not active (status={company.status})"
        )

    return company


async def _load_product_any(
    product_id: UUID, session: AsyncSession
) -> Product:
    """Load product without status check (for tranche payment)."""
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        raise NotFoundError("Product not found")

    return product


async def _load_company_any(
    company_id: UUID, session: AsyncSession
) -> CompanyProfile:
    """Load company without status check (for tranche payment)."""
    stmt = select(CompanyProfile).where(CompanyProfile.id == company_id)
    result = await session.execute(stmt)
    company = result.scalar_one_or_none()

    if company is None:
        raise NotFoundError("Company not found")

    return company


async def _load_user(
    user_id: UUID, session: AsyncSession
) -> User:
    """Load user by ID."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise NotFoundError(f"User {user_id} not found")

    return user


async def _load_template(
    template_id: UUID, session: AsyncSession
) -> ProductInstallment:
    """Load ProductInstallment template (must not be soft-deleted)."""
    stmt = (
        select(ProductInstallment)
        .where(
            ProductInstallment.id == template_id,
            ProductInstallment.is_deleted == False,  # noqa: E712
        )
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()

    if template is None:
        raise NotFoundError("Installment template not found")

    return template


def _resolve_distribution_config(
    product: Product,
    company: CompanyProfile,
) -> dict:  # type: ignore[type-arg]
    """Resolve distribution config from product override or company fallback.

    Same logic as purchases/service.py but without status requirements.
    """
    if product.purchase_config is not None:
        dist = product.purchase_config.get("distribution")
        if dist is not None:
            return dist

    return company.distribution_config


async def _all_tranches_paid(
    plan_id: UUID, session: AsyncSession
) -> bool:
    """Check if all tranches in a plan have been paid."""
    stmt = (
        select(func.count())
        .select_from(InstallmentTranche)
        .where(
            InstallmentTranche.plan_id == plan_id,
            InstallmentTranche.status != InstallmentTrancheStatus.PAID,
        )
    )
    unpaid_count = (await session.execute(stmt)).scalar_one()
    return unpaid_count == 0


async def _award_completion_bonuses(
    plan: InstallmentPlan,
    bonus_units: int,
    agent_bonus_units: int,
    session: AsyncSession,
) -> None:
    """Award completion bonus units via engine.write_transactions().

    Investor gets bonus_units as gift Purchase (paid_cents=0).
    Agent L1 gets agent_bonus_units as gift Purchase (paid_cents=0).
    """
    company = await _load_company_any(plan.company_id, session)
    platform_user = await get_platform_user(session)

    transactions: list[Transaction] = []

    # -- Investor bonus --
    if bonus_units > 0:
        reason = LedgerReason.GIFT.format(
            type="installment_completion",
            reference_id=str(plan.id),
        )
        entries = [
            LedgerEntry(
                user_id=plan.investor_id,
                ledger_type="active",
                amount_cents=0,
                reason=reason,
                origin_payment_id=None,
                frozen_until=None,
            ),
            LedgerEntry(
                user_id=company.user_id,
                ledger_type="passive",
                amount_cents=0,
                reason=reason,
                origin_payment_id=None,
                frozen_until=None,
            ),
        ]
        transactions.append(Transaction(
            reason=reason,
            legal_basis="gift",
            entries=entries,
            units=bonus_units,
        ))

    # -- Agent L1 bonus --
    if agent_bonus_units > 0 and plan.agent_id is not None:
        reason = LedgerReason.GIFT.format(
            type="installment_completion_agent",
            reference_id=str(plan.id),
        )
        entries = [
            LedgerEntry(
                user_id=plan.agent_id,
                ledger_type="active",
                amount_cents=0,
                reason=reason,
                origin_payment_id=None,
                frozen_until=None,
            ),
            LedgerEntry(
                user_id=company.user_id,
                ledger_type="passive",
                amount_cents=0,
                reason=reason,
                origin_payment_id=None,
                frozen_until=None,
            ),
        ]
        transactions.append(Transaction(
            reason=reason,
            legal_basis="gift",
            entries=entries,
            units=agent_bonus_units,
        ))

    if not transactions:
        return

    # Build minimal PurchaseContext for write_transactions.
    # amount_cents=0, all gift fields.
    context = PurchaseContext(
        investor_id=plan.investor_id,
        product_id=plan.product_id,
        company_id=plan.company_id,
        company_user_id=company.user_id,
        platform_user_id=platform_user.id,
        amount_cents=0,
        units=0,
        price_per_unit_cents=plan.price_per_unit_cents,
        distribution_config={"company_pct": 0, "agent_levels": []},
        purchase_config_bonuses=[],
        origin_payment_id=None,
        frozen_until=None,
        agent_chain=[],
        triggered_at=datetime.now(UTC),
    )

    purchases = await engine.write_transactions(
        session=session,
        transactions=transactions,
        context=context,
    )

    # Audit bonus purchases.
    for purchase in purchases:
        await record_audit(
            session=session,
            event="installment.bonus_awarded",
            actor_id=plan.investor_id,
            actor_type="system",
            target_type="purchase",
            target_id=purchase.id,
            data={
                "plan_id": str(plan.id),
                "units": purchase.units,
                "legal_basis": purchase.legal_basis,
            },
        )
