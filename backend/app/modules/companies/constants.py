# =============================================================================
# CBSHOME Backend -- Company Constants (Sprint 4.1, Refactor 2 iter 2.2)
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
