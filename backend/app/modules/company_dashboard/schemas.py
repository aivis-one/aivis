# =============================================================================
# AIVIS.ONE Backend -- Company Dashboard Schemas (Sprint 4.3 / B5)
# =============================================================================
#
# RESPONSE SCHEMAS:
#   PoolEmbedResponse            -- pool fields embedded in the dashboard
#                                   payload. Not the full PoolResponse
#                                   from pools/schemas.py: id and
#                                   company_id are redundant when the
#                                   caller already knows whose dashboard
#                                   they are looking at.
#   CompanyTransactionResponse   -- one Transaction row for the recent
#                                   feed. Mirror of TransactionResponse
#                                   without user_id (also redundant in
#                                   this context).
#   CompanyDashboardResponse     -- GET /api/v1/company/dashboard
#   SalesByMonthEntry            -- one bucket of sales_by_month
#   SalesByProductEntry          -- one row of sales_by_product
#   CompanyAnalyticsResponse     -- GET /api/v1/company/analytics
#
# BalanceResponse:
#   Reused from dashboard/schemas.py (the investor dashboard module).
#   The two payloads have identical semantics -- a {frozen, confirmed}
#   pair of ledger sums in cents -- so a single shared schema avoids
#   OpenAPI emitting two name-mangled types
#   (app__modules__*__schemas__BalanceResponse) which would leak as
#   ugly identifiers into the auto-generated frontend types.
#
# RATIONALE FOR LOCAL TRANSACTION SHAPE:
#   The transactions module's TransactionResponse exposes user_id, which
#   the company dashboard does not need (always == company.user_id). A
#   local shape keeps this endpoint decoupled from changes in
#   transactions/schemas.py.
#
# DECIMAL FOR equity_percent:
#   OptionPool.equity_percent is Numeric(7, 4). Pydantic emits Decimal
#   as a JSON string by default, which is what we want -- preserves
#   precision across the API boundary.
# =============================================================================

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.dashboard.schemas import BalanceResponse

# Re-exported so callers of company_dashboard.schemas don't need to
# know the canonical home of BalanceResponse. Keeps router /
# CompanyDashboardResponse imports tidy.
__all__ = [
    "BalanceResponse",
    "PoolEmbedResponse",
    "CompanyTransactionResponse",
    "CompanyDashboardResponse",
    "SalesByMonthEntry",
    "SalesByProductEntry",
    "CompanyAnalyticsResponse",
]


# ---------------------------------------------------------------------------
# Sub-shapes
# ---------------------------------------------------------------------------


class PoolEmbedResponse(BaseModel):
    """Pool snapshot embedded in the dashboard payload.

    Unlike pools.schemas.PoolResponse, this does not include id or
    company_id -- the dashboard caller already knows whose company
    this is. status is included so the UI can disable pool-edit
    actions on a future archived pool without a second call.
    """

    total_options: int
    equity_percent: Decimal
    consumed: int
    remaining: int
    status: str


class CompanyTransactionResponse(BaseModel):
    """Single row of the recent transactions feed.

    Mirrors transactions.schemas.TransactionResponse minus user_id.
    from_attributes=True so the service can model_validate(orm_row)
    directly; missing optional fields default to None.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    amount_cents: int
    currency: str
    reference_id: UUID | None = None
    reference_type: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# GET /api/v1/company/dashboard
# ---------------------------------------------------------------------------


class CompanyDashboardResponse(BaseModel):
    """Aggregated dashboard for the authenticated company.

    Fields:
      passive_balance: company's earnings ledger split by status.
      total_revenue_cents: SUM(Purchase.paid_cents) for active purchases
        of this company. Gift purchases naturally contribute 0 here.
      total_options_sold: SUM(Purchase.units WHERE legal_basis='sale')
        for active purchases. Gifts are excluded so the number
        reflects commercial activity, not pool consumption (pool
        consumption lives in pool.consumed below).
      products_count: COUNT(Product) for non-archived products.
      pool: active OptionPool snapshot, or None if the company hasn't
        had a pool created yet (newly created company before staff
        runs POST /staff/companies/{id}/pool).
      recent_transactions: last 20 Transaction rows for the company's
        user_id, newest first.
    """

    passive_balance: BalanceResponse
    total_revenue_cents: int
    total_options_sold: int
    products_count: int
    pool: PoolEmbedResponse | None = None
    recent_transactions: list[CompanyTransactionResponse]


# ---------------------------------------------------------------------------
# GET /api/v1/company/analytics
# ---------------------------------------------------------------------------


class SalesByMonthEntry(BaseModel):
    """One bucket of sales_by_month.

    month: 'YYYY-MM' (UTC, derived from Purchase.created_at).
    """

    month: str
    revenue_cents: int
    options_sold: int


class SalesByProductEntry(BaseModel):
    """One row of sales_by_product.

    revenue_cents and options_sold are zero for products that exist
    but have no active sales. Archived products are included too -- the
    point of this list is to show which products do not sell.
    """

    product_id: UUID
    product_name: str
    revenue_cents: int
    options_sold: int


class CompanyAnalyticsResponse(BaseModel):
    """Sales analytics for the authenticated company.

    Fields:
      total_revenue_cents: SUM(paid_cents) on active purchases (lifetime).
      revenue_this_month_cents: SUM(paid_cents) on active purchases
        with created_at >= start of current UTC month.
      total_options_sold: SUM(units WHERE legal_basis='sale') on active
        purchases (lifetime).
      sales_by_month: last 12 months that had at least one sale,
        oldest first (so the UI can render a left-to-right time axis
        without sorting). Empty months are skipped (no zero-padding).
      sales_by_product: ALL products of the company (including archived
        and zero-sales), sorted by revenue_cents DESC. Lets staff see
        what isn't selling at a glance.
    """

    total_revenue_cents: int
    revenue_this_month_cents: int
    total_options_sold: int
    sales_by_month: list[SalesByMonthEntry]
    sales_by_product: list[SalesByProductEntry]
