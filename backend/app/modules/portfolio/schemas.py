# =============================================================================
# AIVIS.ONE Backend -- Portfolio Schemas (Sprint 9.2)
# =============================================================================
#
# RESPONSE SCHEMAS:
#   CompanyPositionResponse      -- per-company position in portfolio list
#   PortfolioResponse            -- list of company positions
#   PurchaseItemResponse         -- single purchase in position detail
#   CompanyPositionDetailResponse -- position + paginated purchases
#
# PRICING LOGIC:
#   avg_price_cents = SUM(paid_cents) / SUM(units WHERE legal_basis='sale')
#   Gift units do not contribute to average price (they are free).
#   If investor has only gift units for a company, avg_price_cents = 0.
#
#   current_price_cents = company.price_per_unit_cents (live from DB)
#   current_value_cents = total_units * current_price_cents
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CompanyPositionResponse(BaseModel):
    """Per-company position in the portfolio."""

    company_id: UUID
    company_name: str
    logo_url: str | None
    total_units: int
    sale_units: int
    gift_units: int
    total_paid_cents: int
    avg_price_cents: int
    current_price_cents: int
    current_value_cents: int
    purchases_count: int


class PortfolioResponse(BaseModel):
    """Full portfolio: list of company positions."""

    positions: list[CompanyPositionResponse]


class PurchaseItemResponse(BaseModel):
    """Single purchase record in the position detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    legal_basis: str
    units: int
    paid_cents: int
    price_per_unit_cents: int
    status: str
    created_at: datetime


class CompanyPositionDetailResponse(BaseModel):
    """Position detail for a single company with paginated purchases."""

    company_id: UUID
    company_name: str
    logo_url: str | None
    total_units: int
    sale_units: int
    gift_units: int
    total_paid_cents: int
    avg_price_cents: int
    current_price_cents: int
    current_value_cents: int
    purchases: list[PurchaseItemResponse]
    total: int
    page: int
    per_page: int
