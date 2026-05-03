# =============================================================================
# CBSHOME Backend -- Product Schemas (Sprint 4.2 + Sprint 6.1 + Sprint F4.1
#                                       + Sprint 4.3 + Sprint 4.4)
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
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - CreateProductRequest.units -> CreateProductRequest.package_size.
#     Semantics unchanged (number of options in one package); the rename
#     removes the ambiguity with "remaining inventory" that the old name
#     carried.
#   - ProductResponse: +pool_id (UUID), units -> package_size. The pool
#     a product belongs to is part of its identity for staff.
#   - PublicProductResponse: units -> package_size, sold_units ->
#     available_packages. Storefront cards now show "X packs available"
#     (computed from the pool) instead of "Y sold" (which was a count of
#     purchases). pool_id is NOT in PublicProductResponse -- it is an
#     internal staff identifier.
#   - UpdateProductRequest stays without size/pool fields: package_size
#     is immutable per spec, and pool reassignment is a future split
#     operation, not an edit.
#
# Sprint 4.3 B4 (Installment Calculator):
#   - InstallmentPreviewRequest -- staff inputs for the calculator
#     (num_tranches, last_tranche_percent, amount_rounding_cents).
#     Bounds for last_tranche_percent come from constants.py so the
#     schema and the calculator never disagree.
#   - InstallmentPreviewSummary / InstallmentPreviewResponse -- the
#     ready-to-submit plan_config and a flat summary for the staff UI.
#     plan_config can be passed verbatim to POST
#     /staff/products/{id}/installments.
#
# Sprint 4.4 CHANGES (B7 UX hardening):
#   - PublicProductResponse: + price_per_pack_cents. Computed in the
#     public router as package_size * price_per_unit_cents. The
#     storefront UX (Sprint 4.4) anchors pricing on the pack, not the
#     unit; precomputing on the server keeps the contract authoritative
#     and avoids client-side multiplication drift.
#   - PublicProductResponse.available_packages: dropped the `= 0`
#     default. The field is required from the router via
#     get_available_packages_map(); a missing populate is a server bug,
#     not a 0-fallback. Frontend mirrors by removing `?? 0`.
#   - PublicProductResponse.company_name: dropped the `= ""` default.
#     The router populates this from a batch CompanyProfile lookup
#     (F4.1). Empty-string was a placeholder for a contract that should
#     never legitimately produce one -- a missing company on a product
#     is a 500, not a "render with empty string". OpenAPI now generates
#     the field as required; frontend gets a stricter type.
#   - PublicProductDetailResponse.installments: dropped the `= []`
#     default. Backend always returns an array (possibly empty) -- the
#     default made OpenAPI mark the field optional, which forced a
#     `?? []` compensation in three frontend call sites. Required + the
#     router passing `installments=[...]` explicitly removes the noise
#     on both sides.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.products.constants import (
    LAST_TRANCHE_PERCENT_MAX,
    LAST_TRANCHE_PERCENT_MIN,
)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateProductRequest(BaseModel):
    """Create a new product for a company."""

    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    name: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    # Sprint 4.3: renamed from `units`. Number of options in one package
    # of this product. Immutable after creation.
    package_size: int = Field(gt=0)
    cover_url: str | None = Field(default=None, max_length=2000)
    purchase_config: dict | None = None  # type: ignore[type-arg]


class UpdateProductRequest(BaseModel):
    """Partial update of product.

    purchase_config triggers financial_operations permission check in router.
    Sprint 4.3: package_size, company_id and pool_id are immutable. Not in
    update schema.
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


class InstallmentPreviewRequest(BaseModel):
    """Staff inputs for the installment calculator (Sprint 4.3 B4).

    Set membership for num_tranches and amount_rounding_cents is
    enforced inside calculator.py so we get a clean BadRequestError
    message; Pydantic does not natively validate membership in a
    frozenset without a custom validator. last_tranche_percent uses
    Field bounds (Pydantic understands ge/le) so the 422 path catches
    obviously bad inputs before the calculator runs.
    """

    model_config = ConfigDict(extra="forbid")

    num_tranches: int = Field(gt=0)
    last_tranche_percent: int = Field(
        ge=LAST_TRANCHE_PERCENT_MIN,
        le=LAST_TRANCHE_PERCENT_MAX,
    )
    amount_rounding_cents: int = Field(gt=0)


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


class InstallmentPreviewSummary(BaseModel):
    """Flat human-friendly numbers for the staff UI (Sprint 4.3 B4).

    Derived from plan_config; here so the UI does not have to traverse
    the tranches list to show key headline numbers (regular vs last
    tranche amount/options, total).
    """

    model_config = ConfigDict(from_attributes=True)

    total_amount_cents: int
    package_size: int
    num_tranches: int
    regular_amount_cents: int
    last_amount_cents: int
    regular_units: int
    last_units: int
    # Surfaced so UI can show "you asked 33%, got 35% (rounding)"
    # without recomputing.
    regular_units_percent: int
    last_units_percent: int


class InstallmentPreviewResponse(BaseModel):
    """Calculator output: ready-to-submit plan_config + summary.

    plan_config is the same shape consumed by POST
    /staff/products/{id}/installments -- staff can edit bonus_units /
    agent_bonus_units in the UI, then submit unchanged.
    """

    model_config = ConfigDict(from_attributes=True)

    plan_config: dict  # type: ignore[type-arg]
    summary: InstallmentPreviewSummary


class ProductResponse(BaseModel):
    """Product info for staff view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    # Sprint 4.3: pool a product belongs to.
    pool_id: UUID
    name: str
    description: str | None
    # Sprint 4.3: renamed from `units`.
    package_size: int
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

    Sprint 4.3: package_size (renamed from units), available_packages
    (renamed from sold_units, now COMPUTED from the pool, not from
    purchase counts). pool_id is intentionally NOT exposed here -- it is
    a staff-side identifier.

    Sprint 4.4: price_per_pack_cents added; available_packages is now
    required (no `= 0` default). Both are populated by the public
    router; missing populate is a server bug, not a soft fallback.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    description: str | None
    # Sprint 4.3: renamed from `units`.
    package_size: int
    price_per_unit_cents: int
    # Sprint 4.4: package_size * price_per_unit_cents. Computed in the
    # router alongside available_packages. Storefront UX anchors price
    # on the pack; this avoids client-side multiplication.
    price_per_pack_cents: int
    cover_url: str | None = None
    # Sprint 4.3: renamed from `sold_units` and re-defined.
    # Sprint 4.4: dropped the `= 0` default -- field is required.
    # Now: floor(pool_remaining / package_size). 0 means sold out.
    # Populated by router via get_available_packages_map().
    available_packages: int

    # Denormalised company fields (Sprint F4.1). Populated by router.
    # Sprint 4.4: company_name dropped its `= ""` default -- a missing
    # company on a product is a 500 (raised in the router as
    # RuntimeError), not a soft empty-string fallback.
    company_name: str
    company_logo_url: str | None = None
    company_cover_url: str | None = None


class PublicProductDetailResponse(PublicProductResponse):
    """Public product detail with installment plans.

    Sprint 4.4: installments is required (no `= []` default). Backend
    always returns an array; the optional-by-default trip through
    OpenAPI was forcing `?? []` on the frontend. Router populates
    explicitly, even if empty.
    """

    installments: list[InstallmentResponse]


class PublicProductListResponse(BaseModel):
    """Paginated list of products (public)."""

    items: list[PublicProductResponse]
    total: int
    page: int
    per_page: int
