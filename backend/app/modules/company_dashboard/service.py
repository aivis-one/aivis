# =============================================================================
# AIVIS.ONE Backend -- Company Dashboard Service (Sprint 4.3 / B5 + Sprint 4.4
#                                                  + Sprint 4.6 hotfix)
# =============================================================================
#
# RESPONSIBILITIES:
#   get_company_dashboard()  -- aggregated dashboard for the company's
#                                main screen: passive balance, sales
#                                totals, products count, embedded pool
#                                snapshot, last 20 transactions
#   get_company_analytics()  -- sales analytics: lifetime totals, this
#                                month's revenue, sales_by_month (last
#                                12 months that had sales), sales_by_product
#                                (ALL products including archived /
#                                zero-sales, sorted by revenue DESC)
#
# Sprint 4.3 NOTE (semantics):
#   `total_options_sold` reports paid-acquisition units only -- both
#   instant SALE and INSTALLMENT_TRANCHE (Sprint 4.6 hotfix). It does
#   NOT include GIFT units, while pool.consumed includes everything.
#   So `consumed - total_options_sold = gift units issued` is the
#   intended interpretation, and it remains true after the hotfix.
#
# Sprint 4.4 CHANGES:
#   - `_POOL_STATUS_ACTIVE` constant removed; imported from
#     pools/constants.py instead.
#   - with_consumed_remaining() now requires `consumed` as an argument.
#     Computed via get_pool_consumed and passed explicitly.
#
# Sprint 4.6 hotfix (paired with portfolio/service.py):
#   `_options_sold_sum` and the `options_aggregate` inside
#   `sales_by_product` previously matched only `legal_basis='sale'`.
#   When an investor paid via installment, their tranche purchase
#   (legal_basis='installment_tranche') was excluded -- the company
#   saw revenue rise (paid_cents was always counted) but
#   `total_options_sold` and `sales_by_product[*].options_sold`
#   stayed at 0. Fix: paid acquisitions now means
#   `legal_basis IN ('sale', 'installment_tranche')`, matching
#   the same definition applied on the portfolio side. Investor's
#   "purchased" view and company's "options sold" view now agree.
#
#   Schema fields (`total_options_sold`, `options_sold`) are
#   unchanged, so no frontend type churn. The values are now correct.
#
# COMMIT RULE (P-01):
#   Service never commits. Read-only queries via get_db_reader.
# =============================================================================

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import CompanyProfile
from app.modules.company_dashboard.schemas import (
    CompanyAnalyticsResponse,
    CompanyDashboardResponse,
    CompanyTransactionResponse,
    PoolEmbedResponse,
    SalesByMonthEntry,
    SalesByProductEntry,
)
from app.modules.dashboard.schemas import BalanceResponse
from app.modules.ledgers.service import get_passive_balance
from app.modules.pools.constants import POOL_STATUS_ACTIVE
from app.modules.pools.models import OptionPool
from app.modules.pools.service import get_pool_consumed, with_consumed_remaining
from app.modules.products.constants import ProductStatus
from app.modules.products.models import Product
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.transactions.models import Transaction

logger = structlog.get_logger()


# Cap for the recent transactions feed.
_RECENT_TRANSACTIONS_LIMIT = 20

# Window for sales_by_month. The query goes back from the start of the
# current UTC month minus 11 months, so the result spans the current
# month plus the 11 preceding ones.
_SALES_BY_MONTH_LOOKBACK_MONTHS = 12


# Sprint 4.6: paid acquisitions for the "options sold" rollup. Both
# instant SALE and INSTALLMENT_TRANCHE put units into the investor's
# hands in exchange for money, so both belong in the company's
# "options sold" line. GIFT is excluded (paid_cents=0 anyway).
_PAID_LEGAL_BASES = (
    PurchaseLegalBasis.SALE,
    PurchaseLegalBasis.INSTALLMENT_TRANCHE,
)


# ---------------------------------------------------------------------------
# Reusable aggregation expressions (case-when sums)
# ---------------------------------------------------------------------------


def _options_sold_sum() -> object:
    """SUM(Purchase.units) for paid acquisitions (sale + installment_tranche).

    Used inside SELECT lists where Purchase rows are already filtered
    to status=active by an outer WHERE clause.

    Sprint 4.6 hotfix: was `legal_basis == SALE` only, which silently
    dropped installment tranche purchases. Now uses the same paired
    semantics as the portfolio service.
    """
    return func.coalesce(
        func.sum(
            case(
                (
                    Purchase.legal_basis.in_(_PAID_LEGAL_BASES),
                    Purchase.units,
                ),
                else_=0,
            )
        ),
        0,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/company/dashboard
# ---------------------------------------------------------------------------


async def get_company_dashboard(
    company: CompanyProfile,
    session: AsyncSession,
) -> CompanyDashboardResponse:
    """Build the dashboard payload for the authenticated company."""
    # -- 1. Passive balance (the company's earnings ledger) --
    passive_bal = await get_passive_balance(session, company.user_id)

    # -- 2. Lifetime revenue + options sold (single query) --
    totals_stmt = (
        select(
            func.coalesce(func.sum(Purchase.paid_cents), 0).label("revenue"),
            _options_sold_sum().label("options_sold"),
        )
        .where(
            Purchase.company_id == company.id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
    )
    totals_row = (await session.execute(totals_stmt)).one()

    # -- 3. Products count (excluding archived) --
    products_stmt = (
        select(func.count())
        .select_from(Product)
        .where(
            Product.company_id == company.id,
            Product.status != ProductStatus.ARCHIVED,
        )
    )
    products_count = int(
        (await session.execute(products_stmt)).scalar_one()
    )

    # -- 4. Active pool (optional -- new companies have no pool yet) --
    pool_stmt = select(OptionPool).where(
        OptionPool.company_id == company.id,
        OptionPool.status == POOL_STATUS_ACTIVE,
    )
    pool = (await session.execute(pool_stmt)).scalar_one_or_none()
    pool_embed: PoolEmbedResponse | None = None
    if pool is not None:
        # DRY with the staff pool router: same helper computes consumed
        # and remaining so the dashboard never disagrees with the staff
        # pool admin view.
        # Sprint 4.4: compute consumed explicitly and feed it to
        # with_consumed_remaining (which no longer runs an implicit SELECT).
        consumed = await get_pool_consumed(pool.company_id, session)
        payload = await with_consumed_remaining(pool, session, consumed=consumed)
        pool_embed = PoolEmbedResponse(
            total_options=payload["total_options"],
            equity_percent=payload["equity_percent"],
            consumed=payload["consumed"],
            remaining=payload["remaining"],
            status=payload["status"],
        )

    # -- 5. Recent transactions (last 20, newest first) --
    txn_stmt = (
        select(Transaction)
        .where(Transaction.user_id == company.user_id)
        .order_by(Transaction.created_at.desc())
        .limit(_RECENT_TRANSACTIONS_LIMIT)
    )
    transactions = list(
        (await session.execute(txn_stmt)).scalars().all()
    )

    return CompanyDashboardResponse(
        passive_balance=BalanceResponse(**passive_bal),
        total_revenue_cents=int(totals_row.revenue),
        total_options_sold=int(totals_row.options_sold),
        products_count=products_count,
        pool=pool_embed,
        recent_transactions=[
            CompanyTransactionResponse.model_validate(t) for t in transactions
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/v1/company/analytics
# ---------------------------------------------------------------------------


def _start_of_current_month_utc(now: datetime) -> datetime:
    """First instant of `now`'s UTC month."""
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _months_lookback_floor(now: datetime, months: int) -> datetime:
    """Start of the UTC month that is `months - 1` months before `now`'s
    month. With months=12 and now in May 2026, this returns 1 Jun 2025.

    Implemented by stepping back one month at a time so we never trip
    over month-length differences (e.g. naive "minus 365 days" misses a
    full month every leap year).
    """
    cursor = _start_of_current_month_utc(now)
    for _ in range(months - 1):
        # Step into the previous month: drop to last day of previous
        # month, then snap to its first day.
        prev = cursor - timedelta(days=1)
        cursor = prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return cursor


async def get_company_analytics(
    company: CompanyProfile,
    session: AsyncSession,
) -> CompanyAnalyticsResponse:
    """Build the sales analytics payload for the authenticated company."""
    now = datetime.now(UTC)
    start_of_month = _start_of_current_month_utc(now)
    lookback_floor = _months_lookback_floor(
        now, _SALES_BY_MONTH_LOOKBACK_MONTHS
    )

    # -- 1. Lifetime totals (revenue + paid options) --
    totals_stmt = (
        select(
            func.coalesce(func.sum(Purchase.paid_cents), 0).label("revenue"),
            _options_sold_sum().label("options_sold"),
        )
        .where(
            Purchase.company_id == company.id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
    )
    totals_row = (await session.execute(totals_stmt)).one()

    # -- 2. Revenue this month --
    this_month_stmt = (
        select(func.coalesce(func.sum(Purchase.paid_cents), 0))
        .where(
            Purchase.company_id == company.id,
            Purchase.status == PurchaseStatus.ACTIVE,
            Purchase.created_at >= start_of_month,
        )
    )
    revenue_this_month = int(
        (await session.execute(this_month_stmt)).scalar_one()
    )

    # -- 3. Sales by month (last 12 months that had sales, oldest first) --
    # date_trunc('month', created_at) gives a TIMESTAMPTZ at the start
    # of that month; we format it to 'YYYY-MM' in Python for the
    # response. Postgres-specific function via SQLAlchemy func.* (still
    # ORM-level, not raw SQL).
    month_col = func.date_trunc("month", Purchase.created_at).label(
        "month_start"
    )
    by_month_stmt = (
        select(
            month_col,
            func.coalesce(func.sum(Purchase.paid_cents), 0).label("revenue"),
            _options_sold_sum().label("options_sold"),
        )
        .where(
            Purchase.company_id == company.id,
            Purchase.status == PurchaseStatus.ACTIVE,
            Purchase.created_at >= lookback_floor,
        )
        .group_by(month_col)
        .order_by(month_col.asc())
    )
    by_month_rows = (await session.execute(by_month_stmt)).all()
    sales_by_month = [
        SalesByMonthEntry(
            month=row.month_start.strftime("%Y-%m"),
            revenue_cents=int(row.revenue),
            options_sold=int(row.options_sold),
        )
        for row in by_month_rows
    ]

    # -- 4. Sales by product (ALL products of the company) --
    # LEFT OUTER JOIN so products without purchases still appear with
    # zero revenue / options. CASE inside SUM filters the join row set
    # without dropping the product (a WHERE on Purchase.status would
    # turn the outer join into an inner one).
    revenue_aggregate = func.coalesce(
        func.sum(
            case(
                (
                    Purchase.status == PurchaseStatus.ACTIVE,
                    Purchase.paid_cents,
                ),
                else_=0,
            )
        ),
        0,
    )
    # Sprint 4.6 hotfix: paid acquisitions = sale + installment_tranche.
    # Same definition as _options_sold_sum() so the per-product breakdown
    # adds up to the lifetime total.
    options_aggregate = func.coalesce(
        func.sum(
            case(
                (
                    (Purchase.status == PurchaseStatus.ACTIVE)
                    & (Purchase.legal_basis.in_(_PAID_LEGAL_BASES)),
                    Purchase.units,
                ),
                else_=0,
            )
        ),
        0,
    )
    by_product_stmt = (
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            revenue_aggregate.label("revenue"),
            options_aggregate.label("options_sold"),
        )
        .outerjoin(Purchase, Purchase.product_id == Product.id)
        .where(Product.company_id == company.id)
        .group_by(Product.id, Product.name)
        # Secondary order by name keeps zero-revenue products in a
        # stable, alphabetical order in the UI list.
        .order_by(revenue_aggregate.desc(), Product.name.asc())
    )
    by_product_rows = (await session.execute(by_product_stmt)).all()
    sales_by_product = [
        SalesByProductEntry(
            product_id=row.product_id,
            product_name=row.product_name,
            revenue_cents=int(row.revenue),
            options_sold=int(row.options_sold),
        )
        for row in by_product_rows
    ]

    return CompanyAnalyticsResponse(
        total_revenue_cents=int(totals_row.revenue),
        revenue_this_month_cents=revenue_this_month,
        total_options_sold=int(totals_row.options_sold),
        sales_by_month=sales_by_month,
        sales_by_product=sales_by_product,
    )
