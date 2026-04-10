# =============================================================================
# CBSHOME Backend -- Purchase Service (Sprint 6.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   execute_purchase()       -- full purchase flow: validate, process, write
#   get_investor_portfolio() -- SUM(paid_cents) for bonus condition checks
#   get_platform_user()      -- load Platform system user
#   get_sold_units_map()     -- COUNT(purchases) per product_id (TD-031)
#
# EXECUTE_PURCHASE FLOW:
#   1. Load Product (must be active)
#   2. Load CompanyProfile (must be active) + Company User
#   3. Load Platform user
#   4. Advisory lock per investor (TOCTOU protection)
#   5. Check investor active balance >= amount
#   6. Compute frozen_until (MAX from frozen active entries)
#   7. Resolve distribution_config (product override or company fallback)
#   8. Build PurchaseContext
#   9. Run ProcessorRegistry -> list[Transaction]
#   10. Verify SUM=0 invariant (done inside registry)
#   11. Write Purchase records + ledger entries atomically
#   12. Record audit events
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# AML NOTE:
#   Purchase saga does NOT call validate_route(). This is a controlled
#   system operation: investor active -> platform passive is always allowed.
#   See CBSHOME-Design-Document.md decision P5-01.
# =============================================================================

from datetime import datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.companies.constants import CompanyStatus
from app.modules.ledgers.models import ActiveLedger, LedgerStatus
from app.modules.ledgers.service import (
    get_active_balance,
    record_active_ledger,
    record_passive_ledger,
)
from app.modules.processors.base import PurchaseContext, Transaction
from app.modules.processors.registry import ProcessorRegistry
from app.modules.products.models import Product, ProductStatus
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def get_platform_user(session: AsyncSession) -> User:
    """Load the Platform system user.

    Raises:
        NotFoundError: If platform user does not exist (seed not run).
    """
    stmt = select(User).where(User.role == UserRole.PLATFORM)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise NotFoundError(
            "Platform system user not found. Run seed_platform.py."
        )

    return user


async def get_investor_portfolio_cents(
    session: AsyncSession,
    investor_id: UUID,
) -> int:
    """Sum of paid_cents from investor's active purchases.

    Used by GiftProcessor for portfolio_size_gte condition.
    """
    stmt = (
        select(func.coalesce(func.sum(Purchase.paid_cents), 0))
        .where(
            Purchase.investor_id == investor_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_sold_units_map(
    session: AsyncSession,
    product_ids: list[UUID],
) -> dict[UUID, int]:
    """Count active purchases per product_id.

    Returns {product_id: count} for the given IDs.
    Products with zero purchases are omitted from the dict.

    Used by public product endpoints for sold_units display (TD-031).
    """
    if not product_ids:
        return {}

    stmt = (
        select(
            Purchase.product_id,
            func.count().label("cnt"),
        )
        .where(
            Purchase.product_id.in_(product_ids),
            Purchase.status == PurchaseStatus.ACTIVE,
            Purchase.legal_basis == PurchaseLegalBasis.SALE,
        )
        .group_by(Purchase.product_id)
    )
    result = await session.execute(stmt)
    return {row.product_id: row.cnt for row in result.all()}


async def _compute_frozen_context(
    session: AsyncSession,
    investor_id: UUID,
) -> tuple[datetime | None, UUID | None]:
    """Compute frozen_until and origin_payment_id for distribution entries.

    Takes MAX(frozen_until) from investor's frozen active_ledger entries.
    Returns (frozen_until, origin_payment_id) from the entry with MAX frozen_until.

    If no frozen entries exist, returns (None, None) -- all funds confirmed.
    """
    stmt = (
        select(
            ActiveLedger.frozen_until,
            ActiveLedger.origin_payment_id,
        )
        .where(
            ActiveLedger.user_id == investor_id,
            ActiveLedger.status == LedgerStatus.FROZEN,
            ActiveLedger.frozen_until.is_not(None),
        )
        .order_by(ActiveLedger.frozen_until.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()

    if row is None:
        return None, None

    return row.frozen_until, row.origin_payment_id


def _resolve_distribution_config(
    product: Product,
    company: CompanyProfile,
) -> dict:  # type: ignore[type-arg]
    """Resolve distribution config: product override or company fallback.

    If product.purchase_config has a "distribution" key, use it.
    Otherwise, fall back to company.distribution_config.
    """
    if product.purchase_config is not None:
        dist = product.purchase_config.get("distribution")
        if dist is not None:
            return dist

    return company.distribution_config


def _resolve_bonuses(product: Product) -> list[dict]:  # type: ignore[type-arg]
    """Extract bonuses from product.purchase_config, or empty list."""
    if product.purchase_config is None:
        return []
    return product.purchase_config.get("bonuses", [])


# ---------------------------------------------------------------------------
# Core purchase execution
# ---------------------------------------------------------------------------


async def execute_purchase(
    product_id: UUID,
    investor: User,
    session: AsyncSession,
    *,
    referral_link_id: UUID | None = None,
) -> list[Purchase]:
    """Execute a full instant purchase.

    Validates balance, runs processors, writes ledger entries and
    Purchase records atomically within the caller's transaction.

    Args:
        product_id: Product to purchase.
        investor: Authenticated investor User.
        session: Active DB session. Caller manages commit (P-01).
        referral_link_id: Optional referral link (stub in Sprint 6.1).

    Returns:
        List of Purchase records created (sale + optional gifts).

    Raises:
        BadRequestError: Insufficient balance, product not active, etc.
        NotFoundError: Product or company not found.
    """
    now = datetime.now(UTC)

    # -- 1. Load Product --
    product = await _load_product(product_id, session)

    # -- 2. Load Company + Company User --
    company = await _load_company(product.company_id, session)
    company_user = await _load_user(company.user_id, session)

    # -- 3. Load Platform user --
    platform_user = await get_platform_user(session)

    # -- 4. Advisory lock: serialize purchases per investor (TOCTOU fix) --
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": investor.id.int & 0x7FFFFFFFFFFFFFFF},
    )

    # -- 5. Check balance --
    amount_cents = product.units * product.price_per_unit_cents
    balance = await get_active_balance(session, investor.id)
    available = balance["frozen"] + balance["confirmed"]

    if available < amount_cents:
        raise BadRequestError(
            f"Insufficient balance: {available} cents available, "
            f"{amount_cents} cents required"
        )

    # -- 6. Compute frozen context --
    frozen_until, origin_payment_id = await _compute_frozen_context(
        session, investor.id
    )

    # -- 7. Resolve configs --
    dist_config = _resolve_distribution_config(product, company)
    bonuses = _resolve_bonuses(product)

    # -- 8. Portfolio for gift conditions --
    portfolio_cents = await get_investor_portfolio_cents(session, investor.id)

    # -- 9. Build context --
    context = PurchaseContext(
        investor_id=investor.id,
        product_id=product.id,
        company_id=company.id,
        company_user_id=company.user_id,
        platform_user_id=platform_user.id,
        amount_cents=amount_cents,
        units=product.units,
        price_per_unit_cents=product.price_per_unit_cents,
        distribution_config=dist_config,
        purchase_config_bonuses=bonuses,
        origin_payment_id=origin_payment_id,
        frozen_until=frozen_until,
        agent_chain=[],  # Stub in Sprint 6.1
        triggered_at=now,
    )

    # -- 10. Run processors --
    registry = ProcessorRegistry(
        investor_portfolio_cents=portfolio_cents,
    )
    transactions = registry.run_all(context)

    # -- 11. Write to DB --
    purchases = await _write_transactions(
        session=session,
        transactions=transactions,
        context=context,
    )

    # -- 12. Audit --
    for purchase in purchases:
        await record_audit(
            session=session,
            event=(
                "purchase.created"
                if purchase.legal_basis == PurchaseLegalBasis.SALE
                else "purchase.gift_created"
            ),
            actor_id=investor.id,
            actor_type="user",
            target_type="purchase",
            target_id=purchase.id,
            data={
                "product_id": str(product.id),
                "company_id": str(company.id),
                "legal_basis": purchase.legal_basis,
                "units": purchase.units,
                "paid_cents": purchase.paid_cents,
            },
        )

    logger.info(
        "purchase_executed",
        investor_id=str(investor.id),
        product_id=str(product.id),
        amount_cents=amount_cents,
        purchase_count=len(purchases),
    )

    return purchases


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_product(
    product_id: UUID, session: AsyncSession
) -> Product:
    """Load product and validate it is active."""
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        raise NotFoundError("Product not found")

    if product.status != ProductStatus.ACTIVE:
        raise BadRequestError(
            f"Product is not available for purchase (status={product.status})"
        )

    return product


async def _load_company(
    company_id: UUID, session: AsyncSession
) -> CompanyProfile:
    """Load company profile and validate it is active."""
    stmt = select(CompanyProfile).where(CompanyProfile.id == company_id)
    result = await session.execute(stmt)
    company = result.scalar_one_or_none()

    if company is None:
        raise NotFoundError("Company not found")

    if company.status != CompanyStatus.ACTIVE:
        raise BadRequestError(
            f"Company is not active (status={company.status})"
        )

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


async def _write_transactions(
    session: AsyncSession,
    transactions: list[Transaction],
    context: PurchaseContext,
) -> list[Purchase]:
    """Write Purchase records and ledger entries for all transactions.

    Each Transaction becomes one Purchase record. Ledger entries from
    the transaction are written via record_active/passive_ledger().

    The "{purchase_id}" placeholder in reason strings is replaced with
    the actual Purchase.id after creation.
    """
    purchases: list[Purchase] = []

    for txn in transactions:
        # Determine paid_cents: 0 for gifts, full amount for sale.
        if txn.legal_basis == PurchaseLegalBasis.GIFT:
            paid_cents = 0
        else:
            paid_cents = context.amount_cents

        # Create Purchase record.
        purchase = Purchase(
            investor_id=context.investor_id,
            product_id=context.product_id,
            company_id=context.company_id,
            legal_basis=txn.legal_basis,
            units=txn.units,
            paid_cents=paid_cents,
            price_per_unit_cents=context.price_per_unit_cents,
            status=PurchaseStatus.ACTIVE,
        )
        session.add(purchase)
        await session.flush()

        # Write ledger entries with real purchase_id in reason.
        purchase_id_str = str(purchase.id)

        for entry in txn.entries:
            reason = entry.reason.replace("{purchase_id}", purchase_id_str)

            # Determine ledger status from frozen_until.
            ledger_status = (
                LedgerStatus.FROZEN
                if entry.frozen_until is not None
                else LedgerStatus.CONFIRMED
            )

            if entry.ledger_type == "active":
                await record_active_ledger(
                    session,
                    user_id=entry.user_id,
                    amount_cents=entry.amount_cents,
                    status=ledger_status,
                    reason=reason,
                    frozen_until=entry.frozen_until,
                    origin_payment_id=entry.origin_payment_id,
                )
            else:
                await record_passive_ledger(
                    session,
                    user_id=entry.user_id,
                    amount_cents=entry.amount_cents,
                    status=ledger_status,
                    reason=reason,
                    frozen_until=entry.frozen_until,
                    origin_payment_id=entry.origin_payment_id,
                )

        purchases.append(purchase)

    return purchases
