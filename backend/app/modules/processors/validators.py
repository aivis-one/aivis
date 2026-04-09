# =============================================================================
# CBSHOME Backend -- Purchase Config Validator (Sprint 6.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Validate purchase_config JSONB on Product.
#
# SCHEMA:
#   {
#     "distribution": {                -- nullable, fallback to Company
#       "company_pct": 0.65,
#       "agent_levels": [0.10, 0.03, 0.01]
#     },
#     "bonuses": [                     -- may be empty []
#       {
#         "condition": "always" | "portfolio_size_gte",
#         "bonus_units_percent": 10,   -- percent of purchased units
#         "funded_by": "company" | "platform",
#         "threshold_cents": 50000     -- required for portfolio_size_gte
#       }
#     ]
#   }
#
# RULES:
#   - distribution: if present, validated same as Company.distribution_config
#   - bonuses: sum(bonus_units_percent) <= 100
#   - funded_by: must be "company" or "platform"
#   - condition: must be "always" or "portfolio_size_gte"
#   - threshold_cents: required when condition = "portfolio_size_gte"
#   - Unknown top-level keys rejected
# =============================================================================

from app.core.exceptions import BadRequestError
from app.modules.companies.constants import validate_distribution_config


_VALID_CONDITIONS = frozenset({"always", "portfolio_size_gte"})
_VALID_FUNDED_BY = frozenset({"company", "platform"})
_ALLOWED_TOP_KEYS = frozenset({"distribution", "bonuses"})
_ALLOWED_BONUS_KEYS = frozenset({
    "condition", "bonus_units_percent", "funded_by", "threshold_cents",
})


def validate_purchase_config(config: dict) -> None:  # type: ignore[type-arg]
    """Validate purchase_config structure and invariants.

    Args:
        config: The purchase_config JSONB value.

    Raises:
        BadRequestError: On any validation failure.
    """
    if not isinstance(config, dict):
        raise BadRequestError("purchase_config must be a JSON object")

    # -- Reject unknown top-level keys --
    extra = set(config.keys()) - _ALLOWED_TOP_KEYS
    if extra:
        raise BadRequestError(
            f"purchase_config contains unknown keys: {extra}"
        )

    # -- distribution (optional) --
    distribution = config.get("distribution")
    if distribution is not None:
        validate_distribution_config(distribution)

    # -- bonuses (optional, defaults to []) --
    bonuses = config.get("bonuses")
    if bonuses is not None:
        _validate_bonuses(bonuses)


def _validate_bonuses(bonuses: list) -> None:  # type: ignore[type-arg]
    """Validate the bonuses array."""
    if not isinstance(bonuses, list):
        raise BadRequestError("purchase_config.bonuses must be a list")

    total_pct = 0.0

    for i, bonus in enumerate(bonuses):
        prefix = f"purchase_config.bonuses[{i}]"

        if not isinstance(bonus, dict):
            raise BadRequestError(f"{prefix} must be a JSON object")

        # Reject unknown keys.
        extra = set(bonus.keys()) - _ALLOWED_BONUS_KEYS
        if extra:
            raise BadRequestError(f"{prefix} contains unknown keys: {extra}")

        # -- condition --
        condition = bonus.get("condition")
        if condition is None:
            raise BadRequestError(f"{prefix}.condition is required")
        if condition not in _VALID_CONDITIONS:
            raise BadRequestError(
                f"{prefix}.condition must be one of: "
                f"{', '.join(sorted(_VALID_CONDITIONS))}"
            )

        # -- bonus_units_percent --
        pct = bonus.get("bonus_units_percent")
        if pct is None:
            raise BadRequestError(
                f"{prefix}.bonus_units_percent is required"
            )
        if not isinstance(pct, (int, float)):
            raise BadRequestError(
                f"{prefix}.bonus_units_percent must be a number"
            )
        if pct <= 0 or pct > 100:
            raise BadRequestError(
                f"{prefix}.bonus_units_percent must be between 0 (exclusive) "
                f"and 100 (inclusive)"
            )
        total_pct += pct

        # -- funded_by --
        funded_by = bonus.get("funded_by")
        if funded_by is None:
            raise BadRequestError(f"{prefix}.funded_by is required")
        if funded_by not in _VALID_FUNDED_BY:
            raise BadRequestError(
                f"{prefix}.funded_by must be one of: "
                f"{', '.join(sorted(_VALID_FUNDED_BY))}"
            )

        # -- threshold_cents (required for portfolio_size_gte) --
        if condition == "portfolio_size_gte":
            threshold = bonus.get("threshold_cents")
            if threshold is None:
                raise BadRequestError(
                    f"{prefix}.threshold_cents is required "
                    f"when condition is 'portfolio_size_gte'"
                )
            if not isinstance(threshold, int) or threshold <= 0:
                raise BadRequestError(
                    f"{prefix}.threshold_cents must be a positive integer"
                )

    # -- Sum of all bonus percentages <= 100 --
    if total_pct > 100:
        raise BadRequestError(
            f"purchase_config.bonuses total bonus_units_percent "
            f"({total_pct:.2f}) exceeds 100"
        )
