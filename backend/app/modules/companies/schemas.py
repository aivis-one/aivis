# =============================================================================
# CBSHOME Backend -- Company Schemas (Sprint 4.1, fix Phase 4, Sprint 4.3,
#                                       Refactor 2 iter 2.2 + 2.3)
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
#   PriceHistoryListResponse  -- paginated price-history list (iter 2.6c B3)
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
#
# Refactor 2 iter 2.3 ADDITIONS (Company Document Templates):
#   - TemplateInboxMetadata    -- _meta.cbsmeta.json format used by
#                                 reconcile_templates / reconcile_platform_templates
#                                 AND, post-MVP, the multipart POST body
#                                 for the template-upload editor (R2 §4.8).
#                                 All fields required -- templates have no
#                                 safety-defaults: a wrong field is a legal
#                                 problem, not a UI nuisance.
#   - TemplateResponse         -- read for staff list. is_platform_default is
#                                 a Pydantic computed_field derived from
#                                 company_id (NULL -> True) so the flag stays
#                                 in sync with the row without service-layer
#                                 plumbing.
#   - TemplateDetailResponse   -- extends TemplateResponse with html_content
#                                 (the bytes of template.html from MinIO,
#                                 utf-8 decoded) and storage_prefix (the
#                                 MinIO folder, useful for staff jumping
#                                 into the Web UI to inspect).
# =============================================================================

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.modules.companies.constants import (
    ATTACHMENT_CATEGORY_REGEX,
    DocumentTemplateKind,
    RoadmapItemKind,
)


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
    """Add a roadmap item to a company (R1 §5).

    `kind` defaults to MILESTONE for backward compatibility with the
    pre-2.4 surface. Per-kind validation is enforced by the
    model_validator below:
      milestone    -- valid_until forbidden. target_date optional.
                      status defaults to 'planned' (service layer).
      event        -- target_date REQUIRED, valid_until REQUIRED,
                      valid_until > target_date.
      announcement -- target_date / valid_until / status all forbidden.

    `cover_storage_key` is intentionally NOT in this body. The cover is
    set via the dedicated multipart endpoint
    PUT /staff/companies/{id}/roadmap/{item_id}/cover.

    Service-level checks (not visible here):
      - linked_product_id must belong to the same company.
      - post_id must reference an existing Post.
    """

    model_config = ConfigDict(extra="forbid")

    # Default keeps existing Staff UI calls that don't send kind working;
    # migration 0033 made the column NOT NULL with the same default.
    kind: RoadmapItemKind = Field(default=RoadmapItemKind.MILESTONE)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    target_date: date | None = None
    valid_until: date | None = None
    # Only meaningful for kind=milestone. Service defaults to "planned"
    # when omitted on a milestone create.
    status: str | None = None
    external_url: str | None = Field(default=None, max_length=2000)
    post_id: UUID | None = None
    linked_product_id: UUID | None = None

    @field_validator("external_url")
    @classmethod
    def _validate_external_url(cls, v: str | None) -> str | None:
        """Reject non-http(s) schemes. Mirrors the posts.cover_url check."""
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("external_url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def _check_kind_rules(self) -> "CreateRoadmapItemRequest":
        """R1 §5 per-kind invariants."""
        if self.kind == RoadmapItemKind.MILESTONE:
            if self.valid_until is not None:
                raise ValueError("valid_until is not allowed for kind=milestone")
        elif self.kind == RoadmapItemKind.EVENT:
            if self.target_date is None:
                raise ValueError("target_date is required for kind=event")
            if self.valid_until is None:
                raise ValueError("valid_until is required for kind=event")
            if self.valid_until <= self.target_date:
                raise ValueError(
                    "valid_until must be after target_date for kind=event"
                )
        elif self.kind == RoadmapItemKind.ANNOUNCEMENT:
            if self.target_date is not None:
                raise ValueError("target_date is not allowed for kind=announcement")
            if self.valid_until is not None:
                raise ValueError("valid_until is not allowed for kind=announcement")
            if self.status is not None:
                raise ValueError("status is not allowed for kind=announcement")
        return self


class UpdateRoadmapItemRequest(BaseModel):
    """Partial update of a roadmap item (R1 §5).

    `kind` is intentionally OMITTED -- it is immutable after create. To
    change kind, Staff soft-deletes the item and creates a new one.

    Per-kind invariants from CreateRoadmapItemRequest are NOT re-checked
    here (we don't know the current kind without a DB read at validation
    time). The service layer re-applies the relevant rules using the
    persisted kind before committing.

    `cover_storage_key` is not in the body for the same reason as the
    create schema -- a dedicated multipart endpoint manages it.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    target_date: date | None = None
    valid_until: date | None = None
    status: str | None = None
    external_url: str | None = Field(default=None, max_length=2000)
    post_id: UUID | None = None
    linked_product_id: UUID | None = None

    @field_validator("external_url")
    @classmethod
    def _validate_external_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("external_url must start with http:// or https://")
        return v


class ReorderRoadmapRequest(BaseModel):
    """Reorder roadmap items by providing ordered list of IDs."""

    model_config = ConfigDict(extra="forbid")

    item_ids: list[UUID]


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class PostSnippetResponse(BaseModel):
    """Embedded Post preview inside a roadmap item (R1 §5).

    Built by the companies service layer from a Post row -- never via
    `from_attributes` because `excerpt` is derived (first 200 chars of
    body, plain text). Kept here in companies/schemas (rather than
    posts/schemas) because the consumer is the roadmap response and
    importing across modules is allowed in one direction only by the
    existing project convention.
    """

    id: UUID
    title: str
    cover_url: str | None = None
    excerpt: str


class RoadmapItemResponse(BaseModel):
    """Single roadmap item (R1 §5 extension).

    `cover_url` is a presigned URL generated by the service layer from
    `cover_storage_key` (None when no cover uploaded). `post` is
    populated when the row has a `post_id` -- the companies service does
    a LEFT JOIN on posts in get_company_detail so this avoids N+1.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # R1 §5 new fields. kind is a String column at the DB level (see
    # migration 0033 + CompanyRoadmapItem.kind) so the response type
    # stays `str` for forward compatibility with future kinds added
    # without a model change.
    kind: str
    title: str
    description: str | None
    target_date: date | None
    valid_until: date | None = None
    status: str
    order: int
    external_url: str | None = None
    post_id: UUID | None = None
    linked_product_id: UUID | None = None
    # Presigned cover URL; None when no cover or when presign fails.
    cover_url: str | None = None
    # Inline Post snippet, populated by the service layer when post_id
    # is set and the post is still present and published.
    post: PostSnippetResponse | None = None
    created_at: datetime
    updated_at: datetime | None


class PriceHistoryResponse(BaseModel):
    """Single price change record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    price_per_unit_cents: int
    changed_at: datetime
    changed_by: UUID


class PriceHistoryListResponse(BaseModel):
    """Paginated price-history list (iter 2.6c B3).

    Wraps PriceHistoryResponse with the same pagination envelope used
    by CompanyListResponse and every other staff list endpoint, so the
    frontend table component can drive both list flows with one
    pagination contract.
    """

    items: list[PriceHistoryResponse]
    total: int
    page: int
    per_page: int


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


class PublicCompanyStatsResponse(BaseModel):
    """Aggregated storefront stats for a company (iter 2.4 R1 §1.6.2).

    Pool numbers come from the company's single active OptionPool;
    a company without an active pool reports zeros (it's a fresh
    "start-state" company that has not yet had a pool issued, which
    is a rare but legal rendering case rather than a 404).

    `price_growth_90d_percent` uses the "stretched window" semantics
    (R1 §1.6.2 decision): the baseline price is the latest
    CompanyPriceHistory row older than 90 days; for companies whose
    full history is shorter than 90 days, the baseline falls back to
    the earliest history row. No history rows at all -> growth = 0.
    Integer-rounded percent (no decimals).
    """

    pool_total_options: int
    options_sold: int
    options_sold_percent: int
    price_growth_90d_percent: int


class PublicCompanyDetailResponse(PublicCompanyResponse):
    """Public company detail with stats and roadmap items.

    iter 2.4 R1 §1.6.2: `stats` is REQUIRED -- the storefront detail
    surface always shows pool / growth numbers, populated by the
    router from get_public_company_stats. Roadmap items carry the
    R1 §5 extension (kind, cover_url, post snippet, ...).
    """

    stats: PublicCompanyStatsResponse
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


# Allowed values for the `language` field. iter 2.4-post mini-fix:
# attachments.language is now NOT NULL with default 'en' (migration
# 0034). Earlier the column was nullable and NULL meant "language-
# agnostic"; the product team standardised on English-as-fallback, so
# 'en' is the universal default and rows with no explicit language at
# upload time land on 'en' via column defaults.
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
    # iter 2.4-post mini-fix: `language` is now required-with-default
    # rather than nullable. An inbox metadata file that omits the
    # field lands on 'en' (universal fallback); a file with explicit
    # null is rejected by AttachmentLanguage Literal validation, which
    # is the desired behaviour -- legacy inbox files carrying null
    # must be normalised before they reach reconcile.
    language: AttachmentLanguage = "en"
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
    # PATCH semantic: field absent = "do not change". The service
    # applies model_dump(exclude_unset=True), so an omitted field
    # never reaches setattr. But Pydantic does NOT distinguish "absent"
    # from "present and null" via the field type alone -- so we need
    # an explicit guard against the wire-shape `{"language": null}`,
    # which would otherwise pass validation AND survive exclude_unset
    # (since the field was set) AND then crash on the NOT NULL column
    # at flush time with a confusing IntegrityError instead of a
    # readable 422.
    #
    # The `| None = None` annotation is preserved for the field-absent
    # case (Pydantic uses the default when the key is missing). The
    # validator below rejects only the explicit-null case.
    language: AttachmentLanguage | None = None
    order: int | None = Field(default=None, ge=0)
    is_published: bool | None = None
    is_public: bool | None = None

    @field_validator("language", mode="before")
    @classmethod
    def _reject_explicit_null_language(cls, v: object) -> object:
        """Reject `{"language": null}` while still letting the field
        be omitted entirely.

        Distinguishes the two cases by what Pydantic passes to the
        validator: the default (also None) is supplied as a sentinel
        when the key is absent. We can't distinguish those two None's
        at the value layer, so we use a wrapper: ANY explicit None
        coming through here is treated as user-supplied. False
        positives (validator runs on the default) cannot happen --
        mode='before' validators are not invoked on field defaults
        in Pydantic v2; they only fire on input values.
        """
        if v is None:
            raise ValueError(
                "language cannot be null -- the column is NOT NULL; "
                "omit the field to keep the current value, or send an "
                "explicit ISO 639-1 code to change it"
            )
        return v


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
    # iter 2.4-post mini-fix: language is NOT NULL on the column.
    # The API surface therefore drops the | None and always emits a
    # concrete ISO 639-1 code. Frontend codegen will pick this up on
    # the next `cbshome update`; until then, frontend reads the
    # field as string | null but only ever sees real strings.
    language: str
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


# ---------------------------------------------------------------------------
# Document templates (Refactor 2 iter 2.3)
# ---------------------------------------------------------------------------
#
# TemplateInboxMetadata covers two surfaces (R2 §4.8):
#   1. _meta.cbsmeta.json companion file inside templates-inbox folders,
#      parsed by reconcile_templates / reconcile_platform_templates via
#      model_validate_json().
#   2. The future post-MVP POST /staff/.../templates upload body, when the
#      UI editor lands. Same schema in both places -- one source of truth.
#
# Unlike AttachmentInboxMetadata, every field is REQUIRED. R2 §4.8 quote:
# "У template'ов нет safety-defaults как у attachments -- ошибки в template
#  = ошибки рендера договоров = юридические проблемы".
#
# `version` and `asset_files` are NOT in the inbox schema:
#   - version is assigned by reconcile (previous active.version + 1).
#   - asset_files is derived by reconcile from the contents of the inbox
#     folder, not provided by the uploader.


# Allowed languages for templates. No NULL -- the 4-stage fallback
# (R2 §4.7) keys on language; a language-agnostic template would never
# match any of the four queries.
TemplateLanguage = Literal["en", "ru", "de", "ar"]


# Statuses an uploader can request via _meta.cbsmeta.json. `archived` is
# intentionally NOT in this set: archiving is a derived state set
# automatically by reconcile when a new active replaces an old one.
TemplateInboxStatus = Literal["draft", "active"]


class TemplateInboxMetadata(BaseModel):
    """Metadata for a CompanyDocumentTemplate.

    Used as:
      - _meta.cbsmeta.json companion file inside the inbox folder
        (R2 §4.8), parsed via model_validate_json() in
        reconcile_templates.py / reconcile_platform_templates.py.
      - post-MVP multipart POST /staff/companies/{id}/templates body
        (form field `metadata` containing the same JSON).

    All fields required. Templates have no safety-defaults -- a wrong
    enum value or missing language would break legal-document rendering
    and is caught upfront rather than papered over.
    """

    model_config = ConfigDict(extra="forbid")

    kind: DocumentTemplateKind
    language: TemplateLanguage
    title: str = Field(min_length=1, max_length=500)
    status: TemplateInboxStatus


class TemplateResponse(BaseModel):
    """Template as seen by staff in the list view (R2 §4.5).

    Excludes html_content and storage_prefix to keep list payloads small;
    use TemplateDetailResponse for the per-template inspection endpoint
    that includes the full HTML body.

    `is_platform_default` is a computed flag: True for the platform
    fallback rows (company_id IS NULL), False for per-company overrides.
    Pydantic recomputes it from company_id on every serialisation, so
    the flag cannot drift away from the row.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID | None
    kind: str
    language: str
    version: int
    title: str
    status: str
    asset_files: list[str]
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_platform_default(self) -> bool:
        """True for platform default rows (company_id IS NULL)."""
        return self.company_id is None


class TemplateDetailResponse(TemplateResponse):
    """Single template with full body for staff inspection (R2 §4.5).

    Adds:
      - html_content: utf-8 decoded body of <storage_prefix>/template.html
                      fetched from MinIO at request time. Read-through the
                      Redis HTML cache (R2 §4.10) so the staff inspect
                      flow shares cache warmth with the renderer.
      - storage_prefix: the MinIO folder path for this template. Useful
                        when staff wants to jump into MinIO Web UI to see
                        the asset files alongside the parsed HTML.
    """

    storage_prefix: str
    html_content: str
