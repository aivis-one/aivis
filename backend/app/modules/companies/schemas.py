# =============================================================================
# CBSHOME Backend -- Company Schemas (Sprint 4.1, fix Phase 4)
# =============================================================================
#
# REQUEST SCHEMAS:
#   CreateCompanyRequest      -- POST /staff/companies
#   UpdateCompanyRequest      -- PATCH /staff/companies/{id} (partial)
#   UpdatePriceRequest        -- PATCH /staff/companies/{id}/price
#   CreateRoadmapItemRequest  -- POST /staff/companies/{id}/roadmap
#   UpdateRoadmapItemRequest  -- PATCH /staff/companies/{id}/roadmap/{item_id}
#   ReorderRoadmapRequest     -- PATCH /staff/companies/{id}/roadmap/reorder
#
# RESPONSE SCHEMAS:
#   CompanyResponse           -- basic company info (list item)
#   CompanyDetailResponse     -- full company + roadmap items
#   CompanyListResponse       -- paginated list
#   RoadmapItemResponse       -- single roadmap item
#   PriceHistoryResponse      -- single price change record
#
# Phase 4 FIX:
#   CreateCompanyRequest.email uses EmailStr (was: str)
# =============================================================================

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateCompanyRequest(BaseModel):
    """Create a new company with user and profile."""

    model_config = ConfigDict(extra="forbid")

    # User credentials for the company account.
    email: EmailStr = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    # Company profile.
    name: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    logo_url: str | None = Field(default=None, max_length=2000)
    cover_url: str | None = Field(default=None, max_length=2000)
    promo_video_url: str | None = Field(default=None, max_length=2000)
    presentation_url: str | None = Field(default=None, max_length=2000)
    price_per_unit_cents: int = Field(gt=0)
    distribution_config: dict  # type: ignore[type-arg]


class UpdateCompanyRequest(BaseModel):
    """Partial update of company profile.

    Only provided fields are updated. distribution_config triggers
    financial_operations permission check in router.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    logo_url: str | None = None
    cover_url: str | None = None
    promo_video_url: str | None = None
    presentation_url: str | None = None
    distribution_config: dict | None = None  # type: ignore[type-arg]
    status: str | None = None


class UpdatePriceRequest(BaseModel):
    """Change company share price (cascades to products)."""

    model_config = ConfigDict(extra="forbid")

    price_per_unit_cents: int = Field(gt=0)


class CreateRoadmapItemRequest(BaseModel):
    """Add a roadmap milestone to a company."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    target_date: date | None = None
    status: str | None = None  # defaults to "planned" in service


class UpdateRoadmapItemRequest(BaseModel):
    """Partial update of a roadmap item."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    target_date: date | None = None
    status: str | None = None


class ReorderRoadmapRequest(BaseModel):
    """Reorder roadmap items by providing ordered list of IDs."""

    model_config = ConfigDict(extra="forbid")

    item_ids: list[UUID]


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class RoadmapItemResponse(BaseModel):
    """Single roadmap item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    target_date: date | None
    status: str
    order: int
    created_at: datetime
    updated_at: datetime | None


class PriceHistoryResponse(BaseModel):
    """Single price change record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    price_per_unit_cents: int
    changed_at: datetime
    changed_by: UUID


class CompanyResponse(BaseModel):
    """Company info for staff (includes distribution_config)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None
    logo_url: str | None
    cover_url: str | None
    promo_video_url: str | None
    presentation_url: str | None
    price_per_unit_cents: int
    distribution_config: dict  # type: ignore[type-arg]
    status: str
    created_at: datetime
    updated_at: datetime | None


class CompanyDetailResponse(CompanyResponse):
    """Full company detail with roadmap items (staff)."""

    roadmap: list[RoadmapItemResponse] = []


class CompanyListResponse(BaseModel):
    """Paginated list of companies (staff)."""

    items: list[CompanyResponse]
    total: int
    page: int
    per_page: int


class PublicCompanyResponse(BaseModel):
    """Company info for public storefront (no distribution_config)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    logo_url: str | None
    cover_url: str | None
    promo_video_url: str | None
    presentation_url: str | None
    price_per_unit_cents: int
    status: str
    created_at: datetime


class PublicCompanyDetailResponse(PublicCompanyResponse):
    """Public company detail with roadmap items (no distribution_config)."""

    roadmap: list[RoadmapItemResponse] = []


class PublicCompanyListResponse(BaseModel):
    """Paginated list of companies (public)."""

    items: list[PublicCompanyResponse]
    total: int
    page: int
    per_page: int
