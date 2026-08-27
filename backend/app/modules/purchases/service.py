# =============================================================================
# AIVIS.ONE Backend -- Purchase Service (Sprint 6.1 + Sprint 6.2 refactor
#                                       + Sprint 4.3 + Sprint 4.4
#                                       + Refactor 2 iter 2.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   execute_purchase()              -- instant purchase: validate + build context
#   get_investor_portfolio_cents    -- SUM(paid_cents) for bonus conditions
#   get_platform_user()             -- load Platform system user
#   get_available_packages_map()    -- floor(pool_remaining / package_size)
#                                      per product_id (Sprint 4.3, replaces
#                                      get_sold_units_map)
#
# Sprint 6.2 REFACTOR:
#   Financial execution core (advisory lock, balance check, registry,
#   write transactions, audit) extracted into purchases/engine.py.
#   execute_purchase() now builds PurchaseContext and delegates to
#   engine.execute(). This allows installments/service.py to reuse
#   the same engine with a differently-built context.
#
# EXECUTE_PURCHASE FLOW (after refactor + Sprint 4.3):
#   0. KYC guard (TD-038)
#   1. Load Product (must be active)
#   2. Load CompanyProfile (must be active) + Company User
#   3. Load Platform user
#   4. Sprint 4.3: load active pool, validate pool_remaining >= package_size.
#      Reject the purchase BEFORE any money moves -- the user sees a
#      clean 400 "sold out" instead of a half-applied transaction.
#   5. Compute frozen context (frozen_until, origin_payment_id)
#   6. Resolve distribution_config (product override or company fallback)
#   7. Resolve bonuses from purchase_config
#   8. Get investor portfolio for gift conditions
#   9. Build PurchaseContext (units = product.package_size,
#      amount_cents = package_size * price)
#   10. Delegate to engine.execute()
#
# Sprint 4.3 NOTES:
#   - get_sold_units_map (COUNT of active purchases per product) replaced
#     by get_available_packages_map (floor of pool_remaining /
#     package_size per product). The new helper takes a list of
#     company_ids alongside product_ids so we can fetch the active pools
#     in a single query rather than one-per-product.
#   - PurchaseContext.units is named `units` (the field stays). What
#     CHANGED is its source: product.package_size (previously product.units,
#     same semantic, renamed column).
#   - (HISTORY) Pool-consumption races were an accepted MVP risk until
#     R51: step 4 now takes pg_advisory_xact_lock keyed by company_id
#     (pools/service.lock_pool) before the capacity check, serializing
#     concurrent buyers and installment-plan creation. NOTE the key is
#     company_id.int masked -- NOT hash(): hash() is randomized per
#     process and never locks across workers. Gift overflow into owner
#     supply (spec §3.7) remains sanctioned and outside the check.
#
# Sprint 4.4 CHANGES:
#   - Removed the local `_POOL_STATUS_ACTIVE` constant -- now imported
#     from pools/constants.py (single source of truth).
#   - Removed the local `_get_active_pool` helper -- it was a near-copy
#     of pools/service.get_active_pool. Replaced with a direct import.
#     The "no upward dependency on pools/service" comment was speculative
#     architecture for a future microservice split that is not on the
#     roadmap; products/service.py already imports from pools, and
#     purchases/service has no fan-out problem.
#   - Removed the local `_get_pool_remaining` helper -- replaced with
#     pools/service.get_pool_remaining (same SQL, public name).
#
# Refactor 2 iter 2.4:
#   - PurchaseContext now carries `investor_language` (R2 §5.1). We
#     read it from investor.language (NOT NULL on User, with "en" as
#     server default for legacy rows) and pass it through to the
#     engine, which uses it for the 4-stage template fallback when
#     snapshotting Purchase.purchase_agreement_template_id.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# AML NOTE:
#   Purchase saga does NOT call validate_route(). This is a controlled
#   system operation: investor active -> platform passive is always allowed.
#   See AIVIS-Design-Document.md decision P5-01.
# =============================================================================

from datetime import datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.comms import comms_configured
from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.companies.constants import CompanyStatus
from app.modules.ledgers.models import ActiveLedger, LedgerStatus
from app.modules.pools.constants import POOL_STATUS_ACTIVE
from app.modules.pools.models import OptionPool
from app.modules.pools.service import get_active_pool, get_pool_remaining, lock_pool
from app.modules.processors.base import PurchaseContext
from app.modules.products.models import Product, ProductStatus
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.purchases import engine
from app.modules.referrals.service import (
    create_attribution,
    get_agent_chain,
    validate_referral_link_id,
)
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


async def get_available_packages_map(
    session: AsyncSession,
    *,
    company_ids: list[UUID],
    product_ids: list[UUID],
) -> dict[UUID, int]:
    """Compute available packages per product from each product's pool.

    Sprint 4.3 replacement for get_sold_units_map.

    Algorithm:
      1. Fetch all active pools for the given company_ids (single SELECT).
      2. Fetch consumed = SUM(Purchase.units) per company_id for active
         purchases, including gifts (single SELECT).
      3. Fetch package_size for each product_id (single SELECT).
      4. For each product:
            pool = pools[product.company_id]
            if no active pool -> 0  (shouldn't happen in steady state;
                                     defensive against half-set-up data)
            remaining = pool.total_options - consumed[company_id]
            available = max(0, remaining // package_size)

    Returns {product_id: available_packages}. Products are present in the
    dict iff they were in product_ids; missing pool / data integrity
    issues result in 0, not an exception (the storefront should not 500
    because one company is misconfigured).

    All inputs may be empty -- returns {} in that case.
    """
    if not product_ids or not company_ids:
        return {}

    # 1. Active pools by company.
    pools_stmt = select(OptionPool).where(
        OptionPool.company_id.in_(company_ids),
        OptionPool.status == POOL_STATUS_ACTIVE,
    )
    pools_result = await session.execute(pools_stmt)
    pools_by_company: dict[UUID, OptionPool] = {}
    for pool in pools_result.scalars().all():
        # If a company somehow has multiple active pools (DB index would
        # have stopped this; this branch is paranoia), keep the first
        # and ignore extras. We do NOT raise here -- the storefront
        # should still render.
        pools_by_company.setdefault(pool.company_id, pool)

    # 2. Consumed per company (all active purchases, gifts included).
    consumed_stmt = (
        select(
            Purchase.company_id,
            func.coalesce(func.sum(Purchase.units), 0).label("consumed"),
        )
        .where(
            Purchase.company_id.in_(company_ids),
            Purchase.status == PurchaseStatus.ACTIVE,
        )
        .group_by(Purchase.company_id)
    )
    consumed_result = await session.execute(consumed_stmt)
    consumed_by_company: dict[UUID, int] = {
        row.company_id: int(row.consumed) for row in consumed_result.all()
    }

    # 3. package_size + company_id per product.
    products_stmt = select(
        Product.id,
        Product.company_id,
        Product.package_size,
    ).where(Product.id.in_(product_ids))
    products_result = await session.execute(products_stmt)

    available_map: dict[UUID, int] = {}
    for row in products_result.all():
        pool = pools_by_company.get(row.company_id)
        if pool is None:
            available_map[row.id] = 0
            continue

        consumed = consumed_by_company.get(row.company_id, 0)
        remaining = pool.total_options - consumed

        if remaining <= 0 or row.package_size <= 0:
            available_map[row.id] = 0
            continue

        available_map[row.id] = remaining // row.package_size

    return available_map


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

    Validates product/company status + pool capacity, builds
    PurchaseContext, and delegates to engine.execute() for the financial
    operation.

    Args:
        product_id: Product to purchase.
        investor: Authenticated investor User.
        session: Active DB session. Caller manages commit (P-01).
        referral_link_id: Optional referral link.

    Returns:
        List of Purchase records created (sale + optional gifts).

    Raises:
        BadRequestError: Insufficient balance, product not active, KYC
            not approved, no active pool, or pool sold out.
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

    # -- 4. Sprint 4.3: pool capacity check BEFORE any money moves. --
    # R51: lock_pool serializes check+write per company -- the
    # pre-R51 "accepted MVP risk" oversell race (two buyers pass the
    # check on the last units) is closed. The xact lock is held until
    # commit, so the Purchase rows written by the engine below land
    # inside the same critical section. Remaining also subtracts
    # ACTIVE installment-plan reservations (pools/service R51).
    #
    # Sprint 4.4: get_active_pool / get_pool_remaining imported
    # from pools/service (was a private duplicate inside this module).
    await lock_pool(company.id, session)
    pool = await get_active_pool(company.id, session)
    pool_remaining = await get_pool_remaining(pool, session)
    if pool_remaining < product.package_size:
        raise BadRequestError(
            f"Sold out: pool has {max(0, pool_remaining)} options remaining, "
            f"package requires {product.package_size}"
        )

    # -- 5. Compute frozen context --
    frozen_until, origin_payment_id = await compute_frozen_context(
        session, investor.id
    )

    # -- 6. Resolve configs --
    dist_config = _resolve_distribution_config(product, company)
    bonuses = _resolve_bonuses(product)

    # -- 7. Portfolio for gift conditions --
    portfolio_cents = await get_investor_portfolio_cents(session, investor.id)

    # -- 8. Build context --
    # Sprint 4.3: source field renamed (product.units -> product.package_size).
    # PurchaseContext.units field name stays; it is "options the investor
    # receives", not a column reference.
    amount_cents = product.package_size * product.price_per_unit_cents

    # Refactor 2 iter 2.4: investor_language drives the engine's
    # template-snapshot fallback (R2 §5.1). User.language is NOT NULL
    # in DB, so investor.language is always a string -- the `or "en"`
    # below is paranoia (handles a hand-built test User without
    # language set) and matches the dataclass default.
    investor_language = investor.language or "en"

    context = PurchaseContext(
        investor_id=investor.id,
        product_id=product.id,
        company_id=company.id,
        company_user_id=company.user_id,
        platform_user_id=platform_user.id,
        amount_cents=amount_cents,
        units=product.package_size,
        price_per_unit_cents=product.price_per_unit_cents,
        distribution_config=dist_config,
        purchase_config_bonuses=bonuses,
        origin_payment_id=origin_payment_id,
        frozen_until=frozen_until,
        agent_chain=await get_agent_chain(
            investor.id,
            session,
            max_depth=len(dist_config.get("agent_levels", [])),
        ),
        triggered_at=now,
        investor_language=investor_language,
    )

    # -- 9. Delegate to engine --
    purchases = await engine.execute(
        context,
        session,
        investor_portfolio_cents=portfolio_cents,
    )

    # Sprint 7.2: validate referral_link_id and record attribution.
    validated_link_id = None
    if referral_link_id is not None:
        validated_link_id = await validate_referral_link_id(
            referral_link_id, session
        )
    sale_purchase = next(
        (p for p in purchases if p.legal_basis != "gift"), purchases[0]
    )
    await create_attribution(sale_purchase.id, validated_link_id, session)

    # Batch 3 (2026-08-27), third aivis producer of notification_request.
    # Scoped to the instant-purchase path only -- installments/service.py's
    # pay_tranche() reaches this same engine.execute() for tranche payments,
    # which are a distinct product moment (a plan payment, not a purchase
    # confirmation) and are NOT covered here; flagged, not silently missed
    # (see installments/service.py's own emitter, batch 3 continued).
    if comms_configured():
        await emit_event(
            session,
            EVENT_NOTIFICATION_REQUEST,
            {
                "idempotency_key": f"purchase-completed:{sale_purchase.id}",
                "type": "purchase.completed",
                "target_type": "user",
                "target_value": str(investor.id),
                "title": "Purchase confirmed",
                "body": (
                    f"Your purchase of {product.name} for "
                    f"${sale_purchase.paid_cents / 100:,.2f} is confirmed."
                ),
            },
        )
        # One notification per GIFT row (legal_basis == "gift") -- a
        # purchase can carry more than one bonus allocation depending on
        # purchase_config, and each is its own row with its own units,
        # so each gets its own idempotency key and its own message
        # rather than folding an unknown-length list into the sale
        # notification's body.
        for gift in purchases:
            if gift.legal_basis != "gift":
                continue
            await emit_event(
                session,
                EVENT_NOTIFICATION_REQUEST,
                {
                    "idempotency_key": f"purchase-gift:{gift.id}",
                    "type": "purchase.gift_received",
                    "target_type": "user",
                    "target_value": str(investor.id),
                    "title": "Bonus units received",
                    "body": (
                        f"You received {gift.units} bonus units of "
                        f"{product.name} as a gift with your purchase."
                    ),
                },
            )

    logger.info(
        "purchase_executed",
        investor_id=str(investor.id),
        product_id=str(product.id),
        amount_cents=amount_cents,
        purchase_count=len(purchases),
        pool_remaining_before=pool_remaining,
    )

    return purchases
