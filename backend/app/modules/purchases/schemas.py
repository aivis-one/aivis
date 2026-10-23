# =============================================================================
# AIVIS.ONE Backend -- Purchase Schemas (Sprint 6.1, updated R-2.2)
# =============================================================================
#
# REQUEST SCHEMAS:
#   CreatePurchaseRequest -- POST /api/v1/products/{id}/purchase
#   StaffReversePurchaseRequest -- POST /staff/purchases/{id}/reverse (R-2.2)
#   StaffGrantGiftRequest -- POST /staff/purchases/gifts
#
# RESPONSE SCHEMAS:
#   PurchaseResponse      -- single purchase record
#   PurchaseListResponse  -- paginated list (future use)
#   PurchaseReversalResponse -- manual reversal result summary (R-2.2)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class StaffReversePurchaseRequest(BaseModel):
    """Request body for manual purchase reversal (R-2.2 Block B)."""

    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for the reversal",
    )


class StaffGrantGiftRequest(BaseModel):
    """Staff grants gift parts to a user.

    The product names the project and the price snapshot the gift
    certificate is rendered against. The recipient must have passed KYC.
    Nothing is credited until the recipient accepts.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    product_id: UUID
    units: int = Field(gt=0, le=1_000_000_000)


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


class PurchaseReversalResponse(BaseModel):
    """Manual purchase reversal result summary (R-2.2 Block B)."""

    purchase_id: UUID
    total_reversed_cents: int
    active_entries_reversed: int
    passive_entries_reversed: int
    units_returned: int
    affected_user_ids: list[UUID]


class GiftListResponse(BaseModel):
    """Gifts waiting for the caller's acceptance."""

    items: list[PurchaseResponse]
    total: int


class PurchasePreviewResponse(BaseModel):
    """Bonus parts one package of a product brings the caller right now."""

    bonus_units: int
    bonus_percent: float
