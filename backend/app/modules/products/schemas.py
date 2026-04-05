# =============================================================================
# CBSHOME Backend -- Product Schemas (Sprint 4.2)
# =============================================================================
#
# REQUEST SCHEMAS:
#   CreateProductRequest       -- POST /staff/products
#   UpdateProductRequest       -- PATCH /staff/products/{id} (partial)
#   UpdateProductStatusRequest -- PATCH /staff/products/{id}/status
#   CreateInstallmentRequest   -- POST /staff/products/{id}/installments
#   UpdateInstallmentRequest   -- PATCH /staff/products/{id}/installments/{inst_id}
#
# RESPONSE SCHEMAS:
#   ProductResponse            -- staff view (includes company_id)
#   ProductDetailResponse      -- staff view + installments
#   ProductListResponse        -- paginated list (staff)
#   PublicProductResponse      -- public storefront (no sensitive data)
#   PublicProductDetailResponse-- public + installments + sold_units stub
#   PublicProductListResponse  -- paginated list (public)
#   InstallmentResponse        -- installment plan template
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
    gift_units: int = Field(default=0, ge=0)


class UpdateProductRequest(BaseModel):
    """Partial update of product.

    gift_units triggers financial_operations permission check in router.
    units and company_id are immutable -- not in update schema.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    gift_units: int | None = Field(default=None, ge=0)


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
    gift_units: int
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
    """Product info for public storefront."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    description: str | None
    units: int
    gift_units: int
    price_per_unit_cents: int
    sold_units: int = 0  # TODO Sprint 6.1: real count from purchases


class PublicProductDetailResponse(PublicProductResponse):
    """Public product detail with installment plans."""

    installments: list[InstallmentResponse] = []


class PublicProductListResponse(BaseModel):
    """Paginated list of products (public)."""

    items: list[PublicProductResponse]
    total: int
    page: int
    per_page: int
