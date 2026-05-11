# =============================================================================
# CBSHOME Backend -- Company Constants (Sprint 4.1, Refactor 2 iter 2.2 + 2.3)
# =============================================================================
#
# COMPANY STATUS:
#   active   -- visible on public storefront
#   hidden   -- created but not yet published
#   archived -- soft-deleted, immutable
#
# ROADMAP ITEM STATUS:
#   planned | in_progress | completed
#
# DISTRIBUTION CONFIG:
#   Validates {"company_pct": float, "agent_levels": [float, ...]}
#   Invariant: company_pct + sum(agent_levels) <= 1.0
#   Remainder goes to Platform automatically (not stored).
#
# STATUS TRANSITIONS:
#   hidden  -> active    (publish)
#   active  -> hidden    (unpublish)
#   active  -> archived  (soft-delete)
#   hidden  -> archived  (soft-delete)
#
# Refactor 2 iter 2.2 ADDITIONS (Company Attachments):
#   ATTACHMENT_CATEGORY_REGEX      -- path-tree regex for `category`
#                                     (max 5 levels, lowercase, no spaces)
#   KNOWN_ATTACHMENT_PATHS         -- recommended path hints surfaced as
#                                     UI chips. Hint only, not a constraint.
#   ALLOWED_ATTACHMENT_MIME_TYPES  -- whitelist for multipart upload
#                                     (R2 Q-ATT-3). Mime strings, not extensions.
#   PUBLIC_LIST_RATE_LIMIT,
#   PUBLIC_DOWNLOAD_RATE_LIMIT     -- (max_requests, window_seconds) tuples
#                                     for rate-limiting public-flow attachment
#                                     endpoints (R2 Q-ATT-2).
#
# Refactor 2 iter 2.3 ADDITIONS (Company Document Templates):
#   DocumentTemplateKind            -- StrEnum: 4 hard-coded kinds (R2 §4.3).
#   TemplateStatus                  -- StrEnum: draft / active / archived (R2 §4.2).
#   TEMPLATE_PLACEHOLDERS           -- per-kind allow-list of Jinja2 variables
#                                      (R2 §4.4). Used by reconcile to validate
#                                      uploaded template.html files.
#   TEMPLATE_ASSET_MIME_WHITELIST   -- mimes accepted as binary assets next
#                                      to template.html (logo / signature /
#                                      stamp). PNG + JPEG only.
#   TEMPLATE_ASSET_EXTENSION_TO_MIME -- ext -> mime resolver used by reconcile
#                                      to classify files in the inbox folder.
# =============================================================================

import enum

from app.core.exceptions import BadRequestError


class CompanyStatus(enum.StrEnum):
    """Company profile lifecycle status."""

    ACTIVE = "active"
    HIDDEN = "hidden"
    ARCHIVED = "archived"


class RoadmapItemStatus(enum.StrEnum):
    """Company roadmap item status."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class RoadmapItemKind(enum.StrEnum):
    """Roadmap item surface kind (R1 §5, iter 2.4).

    A roadmap row carries one of three shapes; the API surface differs
    per kind:
      milestone    -- traditional planned-progress-completed item with
                      target_date. Subject to the planned -> in_progress
                      -> completed state machine. Most existing rows fall
                      here; migration 0033 backfills the column to this
                      value.
      event        -- date-bound event (target_date required, valid_until
                      required, valid_until > target_date). Status is
                      irrelevant; events are shown as long as
                      today <= valid_until.
      announcement -- dateless message (no target_date / valid_until /
                      status). Visible until soft-deleted.

    `kind` is immutable after create. To switch kind, Staff soft-deletes
    the row and creates a fresh one with the new kind.
    """

    MILESTONE = "milestone"
    EVENT = "event"
    ANNOUNCEMENT = "announcement"


# Valid status transitions for CompanyProfile.
VALID_COMPANY_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    CompanyStatus.HIDDEN: frozenset({CompanyStatus.ACTIVE, CompanyStatus.ARCHIVED}),
    CompanyStatus.ACTIVE: frozenset({CompanyStatus.HIDDEN, CompanyStatus.ARCHIVED}),
    CompanyStatus.ARCHIVED: frozenset(),  # terminal state
}


def validate_distribution_config(config: dict) -> None:  # type: ignore[type-arg]
    """Validate distribution_config structure and invariants.

    Expected shape:
        {"company_pct": 0.65, "agent_levels": [0.10, 0.03, 0.01]}

    Rules:
        - company_pct required, float, 0 < company_pct < 1.0
        - agent_levels required, list of floats, each 0 < x < 1.0
        - agent_levels may be empty []
        - company_pct + sum(agent_levels) <= 1.0

    Raises:
        BadRequestError on any violation.
    """
    if not isinstance(config, dict):
        raise BadRequestError("distribution_config must be a JSON object")

    # -- company_pct --
    company_pct = config.get("company_pct")
    if company_pct is None:
        raise BadRequestError("distribution_config.company_pct is required")
    if not isinstance(company_pct, (int, float)):
        raise BadRequestError("distribution_config.company_pct must be a number")
    if not (0 < company_pct < 1.0):
        raise BadRequestError(
            "distribution_config.company_pct must be between 0 and 1.0 (exclusive)"
        )

    # -- agent_levels --
    agent_levels = config.get("agent_levels")
    if agent_levels is None:
        raise BadRequestError("distribution_config.agent_levels is required")
    if not isinstance(agent_levels, list):
        raise BadRequestError("distribution_config.agent_levels must be a list")

    for i, level in enumerate(agent_levels):
        if not isinstance(level, (int, float)):
            raise BadRequestError(
                f"distribution_config.agent_levels[{i}] must be a number"
            )
        if not (0 < level < 1.0):
            raise BadRequestError(
                f"distribution_config.agent_levels[{i}] must be between 0 and 1.0 (exclusive)"
            )

    # -- Invariant: company_pct + sum(agent_levels) <= 1.0 --
    total = company_pct + sum(agent_levels)
    if total > 1.0:
        raise BadRequestError(
            f"distribution_config total ({total:.4f}) exceeds 1.0. "
            f"company_pct ({company_pct}) + sum(agent_levels) ({sum(agent_levels):.4f}) must be <= 1.0"
        )

    # -- Reject unknown keys --
    allowed_keys = {"company_pct", "agent_levels"}
    extra_keys = set(config.keys()) - allowed_keys
    if extra_keys:
        raise BadRequestError(
            f"distribution_config contains unknown keys: {extra_keys}"
        )


# =============================================================================
# Refactor 2 iter 2.2 -- Company Attachments
# =============================================================================

# Path-tree regex for CompanyAttachment.category.
# Format: lowercase a-z + digits + `_-`, segments separated by `/`, max 5 levels.
# Examples that match: "legal/licenses/business", "marketing/presentations",
# "patents", "other".
# Examples that don't: "Legal" (uppercase), "a/b/c/d/e/f" (6 levels),
# "a b" (space), "a/" (trailing slash).
ATTACHMENT_CATEGORY_REGEX: str = r"^[a-z0-9_-]+(/[a-z0-9_-]+){0,4}$"


# Recommended category paths surfaced in Staff UI as chips. Hint only --
# Staff may type custom paths matching ATTACHMENT_CATEGORY_REGEX. Backend
# does NOT enforce membership in this set; the frozen set is exposed via
# OpenAPI / Pydantic for the UI to read.
KNOWN_ATTACHMENT_PATHS: frozenset[str] = frozenset({
    # Legal
    "legal/incorporation",
    "legal/licenses/business",
    "legal/licenses/stock",
    # Marketing
    "marketing/presentations",
    "marketing/onepagers",
    "marketing/press",
    # IP
    "patents",
    # Reports
    "reports/annual",
    "reports/audit",
    "reports/quarterly",
    # Generic
    "other",
})


# Mime-type whitelist for multipart upload (R2 Q-ATT-3).
# Stored as full mime strings (not extensions) so we compare against
# UploadFile.content_type directly.
ALLOWED_ATTACHMENT_MIME_TYPES: frozenset[str] = frozenset({
    # Documents
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",    # docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",          # xlsx
    # Images
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/svg+xml",
    # Video
    "video/mp4",
    "video/webm",
    # Plain text
    "text/plain",
    "text/markdown",
})


# Rate limits for public-flow attachment endpoints (R2 Q-ATT-2).
# Tuple shape: (max_requests, window_seconds). Consumed by
# attachments_public_router via the extended core.rate_limit API.
PUBLIC_LIST_RATE_LIMIT: tuple[int, int] = (60, 60)
PUBLIC_DOWNLOAD_RATE_LIMIT: tuple[int, int] = (300, 60)


# =============================================================================
# Refactor 2 iter 2.3 -- Company Document Templates
# =============================================================================
#
# Templates are Jinja2 HTML files plus companion binary assets (logo,
# signature, stamp) stored in MinIO; the DB row is a metadata pointer
# (R2 §4.2). Unlike attachment categories -- which are free-form within a
# regex -- template kinds are a hard-coded enum because the renderer
# branches on `kind` and the placeholder context is kind-specific
# (R2 §4.3 / §4.4).


class DocumentTemplateKind(enum.StrEnum):
    """Document template kinds. Maps onto Purchase.legal_basis for the
    per-purchase variants; OWNERSHIP_CERTIFICATE is the live aggregate.

    R2 §4.3:
      purchase_agreement       -> Purchase.legal_basis = sale
      gift_certificate         -> Purchase.legal_basis = gift
      installment_subcontract  -> Purchase.legal_basis = installment_tranche
      ownership_certificate    -> live aggregate of investor's purchases
                                  for one company (no per-purchase snapshot)
    """

    PURCHASE_AGREEMENT = "purchase_agreement"
    GIFT_CERTIFICATE = "gift_certificate"
    INSTALLMENT_SUBCONTRACT = "installment_subcontract"
    OWNERSHIP_CERTIFICATE = "ownership_certificate"


class TemplateStatus(enum.StrEnum):
    """Template lifecycle status (R2 §4.2).

    State machine:
      draft  <-> active
      draft   -> archived
      active  -> archived

    When reconcile activates a new template for a (company_id, kind, lang)
    triple, the previous active row is automatically archived.
    """

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


# Per-kind Jinja2 placeholder allow-list (R2 §4.4).
#
# Reconcile uses this to validate uploaded template.html: any undeclared
# variable found in the parsed AST must be in this set OR equal to
# "asset_data_uri" (the registered Jinja-global function). Anything else
# is a user typo or an attempt to reach into the rendering process and
# blocks activation.
#
# The exact set of variables passed at render time is set by the rendering
# code in 2.4 -- the contract here is "no template can reference a variable
# the renderer has not been taught to provide". `purchases` is a list of
# objects iterated by Jinja inside the template; we only validate top-level
# names, attribute access on each `purchases[*]` element is the template's
# responsibility.
TEMPLATE_PLACEHOLDERS: dict[DocumentTemplateKind, frozenset[str]] = {
    DocumentTemplateKind.PURCHASE_AGREEMENT: frozenset({
        "investor_name",
        "investor_email",
        "company_name",
        "company_legal_name",
        "product_name",
        "units",
        "paid_cents",
        "price_per_unit_cents",
        "purchase_date",
        "certificate_number",
        "legal_basis",
    }),
    DocumentTemplateKind.GIFT_CERTIFICATE: frozenset({
        "investor_name",
        "investor_email",
        "company_name",
        "company_legal_name",
        "product_name",
        "units",
        "paid_cents",
        "price_per_unit_cents",
        "purchase_date",
        "certificate_number",
        "legal_basis",
    }),
    DocumentTemplateKind.INSTALLMENT_SUBCONTRACT: frozenset({
        "investor_name",
        "investor_email",
        "company_name",
        "company_legal_name",
        "product_name",
        "units",
        "paid_cents",
        "price_per_unit_cents",
        "purchase_date",
        "certificate_number",
        "legal_basis",
    }),
    DocumentTemplateKind.OWNERSHIP_CERTIFICATE: frozenset({
        "investor_name",
        "company_name",
        "total_units",
        "sale_units",
        "gift_units",
        "total_paid_cents",
        "current_value_cents",
        "as_of_date",
        "purchases",
    }),
}


# Allowed mime-types for files sitting next to template.html in the
# template's MinIO folder (logo.png, signature.png, stamp.png and similar).
#
# PNG + JPEG only. SVG is intentionally excluded -- xhtml2pdf does not
# render SVG reliably, so an SVG asset would silently break PDF output
# (and only PDF; HTML preview would still look fine, masking the bug).
TEMPLATE_ASSET_MIME_WHITELIST: frozenset[str] = frozenset({
    "image/png",
    "image/jpeg",
})


# Filename-extension -> mime resolver used by the template reconcile
# scripts when classifying files in the inbox folder. Keys MUST be the
# full extension including the leading dot, lowercase. The set of values
# MUST be a subset of TEMPLATE_ASSET_MIME_WHITELIST.
TEMPLATE_ASSET_EXTENSION_TO_MIME: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
