# =============================================================================
# CBSHOME Backend -- Company Constants (Sprint 4.1)
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
