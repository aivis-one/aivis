# =============================================================================
# AIVIS.ONE Backend -- Installment Schemas (Sprint 6.2)
# =============================================================================
#
# REQUEST SCHEMAS:
#   CreateInstallmentPlanRequest -- POST /api/v1/products/{id}/installment
#
# RESPONSE SCHEMAS:
#   InstallmentTrancheResponse   -- single tranche within a plan
#   InstallmentPlanResponse      -- plan summary (for list endpoint)
#   InstallmentPlanDetailResponse -- plan with tranches (for detail endpoint)
#   InstallmentPlanListResponse  -- paginated list of plans
# =============================================================================

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateInstallmentPlanRequest(BaseModel):
    """Create an installment plan for a product.

    product_installment_id: which template to use.
    referral_link_id: optional referral (Sprint 7.2 stub).
    """

    model_config = ConfigDict(extra="forbid")

    product_installment_id: UUID
    referral_link_id: UUID | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class InstallmentTrancheResponse(BaseModel):
    """Single tranche within an installment plan."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    number: int
    due_date: date
    amount_cents: int
    units_unlocked: int
    status: str
    paid_at: datetime | None
    purchase_id: UUID | None


class InstallmentPlanResponse(BaseModel):
    """Installment plan summary (for list endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    investor_id: UUID
    product_id: UUID
    company_id: UUID
    product_installment_id: UUID
    total_price_cents: int
    total_units: int
    price_per_unit_cents: int
    status: str
    created_at: datetime
    completed_at: datetime | None
    defaulted_at: datetime | None


class InstallmentPlanDetailResponse(InstallmentPlanResponse):
    """Installment plan with tranches (for detail endpoint)."""

    tranches: list[InstallmentTrancheResponse] = []


class InstallmentPlanListResponse(BaseModel):
    """Paginated list of installment plans."""

    items: list[InstallmentPlanResponse]
    total: int
    page: int
    per_page: int
