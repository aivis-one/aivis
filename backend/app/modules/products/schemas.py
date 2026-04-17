# =============================================================================
# CBSHOME Backend -- Product Schemas (Sprint 4.2 + Sprint 6.1 + Sprint F4.1)
# =============================================================================
#
# Sprint 6.1 CHANGES:
#   - Removed gift_units from CreateProductRequest, UpdateProductRequest,
#     ProductResponse, PublicProductResponse
#   - Added purchase_config to CreateProductRequest, UpdateProductRequest,
#     ProductResponse
#   - PublicProductResponse does NOT expose purchase_config (business-sensitive)
#
# Sprint F4.1 CHANGES:
#   - Added cover_url to CreateProductRequest, UpdateProductRequest,
#     ProductResponse, PublicProductResponse.
#   - Added denormalised company fields to PublicProductResponse:
#       company_name, company_logo_url, company_cover_url.
#     Populated by the public router via a batch CompanyProfile lookup so
#     the storefront can render cards without a second round-trip.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateProductRequest(BaseModel):
    """Create a new product for a company."""

    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    name: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    units: int = Field(gt=0)
    cover_url: str | None = Field(default=None, max_length=2000)
    purchase_config: dict | None = None  # type: ignore[type-arg]


class UpdateProductRequest(BaseModel):
    """Partial update of product.

    purchase_config triggers financial_operations permission check in router.
    units and company_id are immutable -- not in update schema.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    cover_url: str | None = Field(default=None, max_length=2000)
    purchase_config: dict | None = None  # type: ignore[type-arg]


class UpdateProductStatusRequest(BaseModel):
    """Change product status."""

    model_config = ConfigDict(extra="forbid")

    status: str


class CreateInstallmentRequest(BaseModel):
    """Add an installment plan template to a product."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)
    plan_config: dict  # type: ignore[type-arg]


class UpdateInstallmentRequest(BaseModel):
    """Update an installment plan template."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=500)
    plan_config: dict | None = None  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class InstallmentResponse(BaseModel):
    """Installment plan template."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    name: str
    plan_config: dict  # type: ignore[type-arg]
    created_at: datetime


class ProductResponse(BaseModel):
    """Product info for staff view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    description: str | None
    units: int
    cover_url: str | None
    purchase_config: dict | None  # type: ignore[type-arg]
    price_per_unit_cents: int
    status: str
    created_at: datetime
    updated_at: datetime | None


class ProductDetailResponse(ProductResponse):
    """Full product detail with installment plans (staff)."""

    installments: list[InstallmentResponse] = []


class ProductListResponse(BaseModel):
    """Paginated list of products (staff)."""

    items: list[ProductResponse]
    total: int
    page: int
    per_page: int


class PublicProductResponse(BaseModel):
    """Product info for public storefront.

    company_name / company_logo_url / company_cover_url are denormalised
    from CompanyProfile by the public router (Sprint F4.1) so the
    storefront can render a card without a second API call.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    description: str | None
    units: int
    price_per_unit_cents: int
    cover_url: str | None = None
    sold_units: int = 0  # Populated by router from Purchase count (TD-031)

    # Denormalised company fields (Sprint F4.1). Populated by router.
    company_name: str = ""
    company_logo_url: str | None = None
    company_cover_url: str | None = None


class PublicProductDetailResponse(PublicProductResponse):
    """Public product detail with installment plans."""

    installments: list[InstallmentResponse] = []


class PublicProductListResponse(BaseModel):
    """Paginated list of products (public)."""

    items: list[PublicProductResponse]
    total: int
    page: int
    per_page: int
