# =============================================================================
# CBSHOME Backend -- Company Schemas (Sprint 4.1, fix Phase 4, Sprint 4.3,
#                                       Refactor 2 iter 2.2)
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
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - CreateCompanyRequest: +total_supply (BigInt > 0), +shares_per_option
#     (int > 0). Both required at creation.
#   - UpdateCompanyRequest: NO total_supply / shares_per_option here.
#     A change in total_supply is a pool-level operation (PATCH
#     /staff/companies/{id}/pool). A change in shares_per_option is a
#     split (future scope, see CBSHOME-Share-Pool-Refactor.md §4).
#     Allowing scalar updates here would break the invariant
#     `pool.equity_percent = pool.total_options / company.total_supply`.
#   - CompanyResponse / PublicCompanyResponse: +total_supply,
#     +shares_per_option. Public storefront needs them so the storefront
#     can show how many options the company has issued and how that
#     relates to the pool size shown on a product card.
#
# Refactor 2 iter 2.2 ADDITIONS (Company Attachments):
#   - AttachmentInboxMetadata   -- cbsmeta.json format AND multipart POST/PATCH
#                                  body (R2 §3.7). One schema, two surfaces.
#   - AttachmentPatchBody       -- subset for PATCH metadata (everything Optional).
#   - AttachmentResponse        -- read for auth-flow + public-flow. Excludes
#                                  storage_key / created_by / is_deleted to
#                                  minimise public surface.
#   - StaffAttachmentResponse   -- read for staff-flow. Extends with
#                                  storage_key, created_by_id, is_deleted.
# =============================================================================

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.companies.constants import ATTACHMENT_CATEGORY_REGEX


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

    # Sprint 4.3: supply config.
    # total_supply -- total number of options covering 100% of company shares.
    # shares_per_option -- denomination ratio (default 1: one option = one share).
    total_supply: int = Field(gt=0)
    shares_per_option: int = Field(default=1, gt=0)


class UpdateCompanyRequest(BaseModel):
    """Partial update of company profile.

    Only provided fields are updated. distribution_config triggers
    financial_operations permission check in router.

    Sprint 4.3: total_supply and shares_per_option are NOT in this schema.
    Pool size changes happen via PATCH /staff/companies/{id}/pool, and a
    shares_per_option change is a split (future scope).
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
    # Sprint 4.3: supply.
    total_supply: int
    shares_per_option: int
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
    # Sprint 4.3: supply -- public storefront shows total_supply alongside
    # the per-product available_packages so investors see the company's
    # full issuance, not just the pool slice.
    total_supply: int
    shares_per_option: int
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


# ---------------------------------------------------------------------------
# Attachments (Refactor 2 iter 2.2)
# ---------------------------------------------------------------------------
#
# AttachmentInboxMetadata serves both the cbsmeta.json companion-file format
# (R2 §3.7, used by reconcile_attachments.py) and the multipart POST/replace
# body shape (Staff API). Single schema -- one source of truth -- so the
# inbox flow and the future UI-driven flow stay byte-compatible.
#
# Defaults are safety-first per R2 §3.7: a freshly seeded attachment is
# invisible to investors until staff explicitly flips is_published=true.
#
# `original_filename` is intentionally NOT a field here: for multipart it
# comes from UploadFile.filename, for inbox it comes from the file sitting
# next to the cbsmeta.json. Decoupling that field from the metadata schema
# keeps the JSON portable across companies / uploads.


# Allowed values for the `language` field. NULL = language-agnostic.
AttachmentLanguage = Literal["en", "ru", "de", "ar"]


class AttachmentInboxMetadata(BaseModel):
    """Metadata for a CompanyAttachment.

    Used as:
      - cbsmeta.json companion-file body (R2 §3.7), parsed via
        model_validate_json() in reconcile_attachments.py.
      - multipart POST /staff/companies/{id}/attachments body
        (form field `metadata` containing the same JSON).
      - multipart PATCH /staff/.../{att_id}/replace body
        (same form field).

    Required: title only. Everything else has safety-first defaults.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    category: str = Field(
        default="unsorted",
        max_length=200,
        pattern=ATTACHMENT_CATEGORY_REGEX,
    )
    language: AttachmentLanguage | None = None
    order: int = Field(default=0, ge=0)
    is_published: bool = False
    is_public: bool = False


class AttachmentPatchBody(BaseModel):
    """Partial update of attachment metadata.

    Used by PATCH /staff/companies/{id}/attachments/{att_id}.

    Every field is optional; the service applies model_dump(exclude_unset=True)
    and only mutates fields that were explicitly sent. `description` accepts
    explicit null to clear the value.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(
        default=None,
        max_length=200,
        pattern=ATTACHMENT_CATEGORY_REGEX,
    )
    language: AttachmentLanguage | None = None
    order: int | None = Field(default=None, ge=0)
    is_published: bool | None = None
    is_public: bool | None = None


class AttachmentResponse(BaseModel):
    """Attachment as seen by investors / public consumers.

    Excludes storage_key (internal MinIO path), created_by (audit-only
    identity), and is_deleted (always False for these flows -- soft-deleted
    rows are filtered out by the service layer).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    category: str
    language: str | None
    title: str
    description: str | None
    original_filename: str
    mime_type: str
    file_size_bytes: int
    order: int
    is_published: bool
    is_public: bool
    created_at: datetime
    updated_at: datetime | None


class StaffAttachmentResponse(AttachmentResponse):
    """Attachment as seen by staff: includes operational fields hidden
    from auth/public flows.

    The model column is `created_by` (UUID NOT NULL today, FK ondelete=RESTRICT);
    we expose it as `created_by_id` at the API boundary for naming clarity
    and type it as Optional to leave room for a future ondelete=SET NULL.
    `validation_alias="created_by"` lets Pydantic populate this field from
    the ORM attribute without renaming the column.
    """

    storage_key: str
    is_deleted: bool
    created_by_id: UUID | None = Field(
        default=None,
        validation_alias="created_by",
    )
