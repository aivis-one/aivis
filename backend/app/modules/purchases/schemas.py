# =============================================================================
# CBSHOME Backend -- Purchase Schemas (Sprint 6.1)
# =============================================================================
#
# REQUEST SCHEMAS:
#   CreatePurchaseRequest -- POST /api/v1/products/{id}/purchase
#
# RESPONSE SCHEMAS:
#   PurchaseResponse      -- single purchase record
#   PurchaseListResponse  -- paginated list (future use)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreatePurchaseRequest(BaseModel):
    """Instant purchase of a product.

    referral_link_id: optional referral link (Sprint 7.2).
    Omit for organic purchase.
    """

    model_config = ConfigDict(extra="forbid")

    referral_link_id: UUID | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class PurchaseResponse(BaseModel):
    """Single purchase record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    investor_id: UUID
    product_id: UUID
    company_id: UUID
    legal_basis: str
    units: int
    paid_cents: int
    price_per_unit_cents: int
    status: str
    created_at: datetime


class PurchaseListResponse(BaseModel):
    """Paginated list of purchases."""

    items: list[PurchaseResponse]
    total: int
    page: int
    per_page: int
