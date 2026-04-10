# =============================================================================
# CBSHOME Backend -- Purchase Service (Sprint 6.1 + Sprint 6.2 refactor)
# =============================================================================
#
# RESPONSIBILITIES:
#   execute_purchase()           -- instant purchase: validate + build context
#   get_investor_portfolio_cents -- SUM(paid_cents) for bonus conditions
#   get_platform_user()          -- load Platform system user
#   get_sold_units_map()         -- COUNT(purchases) per product_id (TD-031)
#
# Sprint 6.2 REFACTOR:
#   Financial execution core (advisory lock, balance check, registry,
#   write transactions, audit) extracted into purchases/engine.py.
#   execute_purchase() now builds PurchaseContext and delegates to
#   engine.execute(). This allows installments/service.py to reuse
#   the same engine with a differently-built context.
#
# EXECUTE_PURCHASE FLOW (after refactor):
#   0. KYC guard (TD-038)
#   1. Load Product (must be active)
#   2. Load CompanyProfile (must be active) + Company User
#   3. Load Platform user
#   4. Compute frozen context (frozen_until, origin_payment_id)
#   5. Resolve distribution_config (product override or company fallback)
#   6. Resolve bonuses from purchase_config
#   7. Get investor portfolio for gift conditions
#   8. Build PurchaseContext
#   9. Delegate to engine.execute()
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.companies.constants import CompanyStatus
from app.modules.ledgers.models import ActiveLedger, LedgerStatus
from app.modules.processors.base import PurchaseContext
from app.modules.products.models import Product, ProductStatus
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.purchases import engine
from app.modules.users.models import KYCStatus, User, UserRole

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers (public -- used by other modules)
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


# ---------------------------------------------------------------------------
# Frozen context computation
# ---------------------------------------------------------------------------


async def compute_frozen_context(
    session: AsyncSession,
    investor_id: UUID,
) -> tuple[datetime | None, UUID | None]:
    """Compute frozen_until and origin_payment_id for distribution entries.

    Takes MAX(frozen_until) from investor's frozen active_ledger entries.
    Returns (frozen_until, origin_payment_id) from the entry with MAX frozen_until.

    If no frozen entries exist, returns (None, None) -- all funds confirmed.

    Public: also used by installments/service.py for tranche payments.
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

    Validates product/company status, builds PurchaseContext, and
    delegates to engine.execute() for the financial operation.

    Args:
        product_id: Product to purchase.
        investor: Authenticated investor User.
        session: Active DB session. Caller manages commit (P-01).
        referral_link_id: Optional referral link (stub in Sprint 6.1).

    Returns:
        List of Purchase records created (sale + optional gifts).

    Raises:
        BadRequestError: Insufficient balance, product not active, KYC not approved.
        NotFoundError: Product or company not found.
    """
    now = datetime.now(UTC)

    # -- 0. KYC guard (TD-038) --
    if investor.kyc_status != KYCStatus.APPROVED:
        raise BadRequestError(
            "KYC verification required before purchase"
        )

    # -- 1. Load Product (must be active) --
    product = await _load_product(product_id, session)

    # -- 2. Load Company (must be active) + Company User --
    company = await _load_company(product.company_id, session)
    company_user = await _load_user(company.user_id, session)

    # -- 3. Load Platform user --
    platform_user = await get_platform_user(session)

    # -- 4. Compute frozen context --
    frozen_until, origin_payment_id = await compute_frozen_context(
        session, investor.id
    )

    # -- 5. Resolve configs --
    dist_config = _resolve_distribution_config(product, company)
    bonuses = _resolve_bonuses(product)

    # -- 6. Portfolio for gift conditions --
    portfolio_cents = await get_investor_portfolio_cents(session, investor.id)

    # -- 7. Build context --
    amount_cents = product.units * product.price_per_unit_cents

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

    # -- 8. Delegate to engine --
    purchases = await engine.execute(
        context,
        session,
        investor_portfolio_cents=portfolio_cents,
    )

    logger.info(
        "purchase_executed",
        investor_id=str(investor.id),
        product_id=str(product.id),
        amount_cents=amount_cents,
        purchase_count=len(purchases),
    )

    return purchases
