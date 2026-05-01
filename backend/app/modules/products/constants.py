# =============================================================================
# CBSHOME Backend -- Product Constants (Sprint 4.2 + Sprint 6.2 + Sprint 4.3)
# =============================================================================
#
# PRODUCT STATUS:
#   active   -- visible on public storefront
#   hidden   -- created but not yet published
#   archived -- soft-deleted, immutable
#
# STATUS TRANSITIONS:
#   hidden  -> active    (publish)
#   active  -> hidden    (unpublish)
#   active  -> archived  (soft-delete)
#   hidden  -> archived  (soft-delete)
#
# PLAN CONFIG VALIDATION:
#   Validates plan_config JSONB against product/company context.
#   Invariants:
#     len(tranches) >= 2
#     all amount_cents > 0
#     all units_percent > 0
#     sum(amount_cents) == product.package_size * company.price_per_unit_cents
#     sum(units_percent) == 100
#     sum(units_percent[i] * product_units // 100) == product_units  (Sprint 6.2)
#     bonus_units >= 0
#     agent_bonus_units >= 0
#
# Sprint 4.3 NOTE (TD-071 / Share Pool Refactor):
#   Product.units was renamed to Product.package_size.
#   The validate_plan_config() parameter name `product_units` STAYS to
#   avoid touching every test fixture that passes it as a kwarg --
#   parameter name is just a label, what matters is that callers pass
#   `product.package_size` as the value (see products/service.py and
#   the installment calculator in B4).
# =============================================================================

import enum

from app.core.exceptions import BadRequestError


class ProductStatus(enum.StrEnum):
    """Product lifecycle status."""

    ACTIVE = "active"
    HIDDEN = "hidden"
    ARCHIVED = "archived"


# Valid status transitions for Product.
VALID_PRODUCT_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    ProductStatus.HIDDEN: frozenset({ProductStatus.ACTIVE, ProductStatus.ARCHIVED}),
    ProductStatus.ACTIVE: frozenset({ProductStatus.HIDDEN, ProductStatus.ARCHIVED}),
    ProductStatus.ARCHIVED: frozenset(),  # terminal state
}


def validate_plan_config(
    config: dict,  # type: ignore[type-arg]
    product_units: int,
    price_per_unit_cents: int,
) -> None:
    """Validate plan_config JSONB structure and invariants.

    Expected shape:
        {
            "tranches": [
                {"amount_cents": int, "units_percent": int},
                ...
            ],
            "bonus_units": int,
            "agent_bonus_units": int
        }

    Args:
        config: plan_config dict to validate.
        product_units: Product.package_size (the package size). The
            parameter name is `product_units` for backwards-compat with
            existing test call sites; semantically this is the package
            size of the product. Sprint 4.3 renamed the column itself
            (units -> package_size) but kept this kwarg name.
        price_per_unit_cents: Product.price_per_unit_cents (current price).

    Raises:
        BadRequestError on any violation.
    """
    if not isinstance(config, dict):
        raise BadRequestError("plan_config must be a JSON object")

    # -- tranches --
    tranches = config.get("tranches")
    if tranches is None:
        raise BadRequestError("plan_config.tranches is required")
    if not isinstance(tranches, list):
        raise BadRequestError("plan_config.tranches must be a list")
    if len(tranches) < 2:
        raise BadRequestError(
            "plan_config.tranches must have at least 2 entries"
        )

    for i, tranche in enumerate(tranches):
        if not isinstance(tranche, dict):
            raise BadRequestError(
                f"plan_config.tranches[{i}] must be a JSON object"
            )

        amount = tranche.get("amount_cents")
        if not isinstance(amount, int) or amount <= 0:
            raise BadRequestError(
                f"plan_config.tranches[{i}].amount_cents must be a positive integer"
            )

        units_pct = tranche.get("units_percent")
        if not isinstance(units_pct, int) or units_pct <= 0:
            raise BadRequestError(
                f"plan_config.tranches[{i}].units_percent must be a positive integer"
            )

        # Reject unknown keys in tranche.
        allowed_tranche_keys = {"amount_cents", "units_percent"}
        extra = set(tranche.keys()) - allowed_tranche_keys
        if extra:
            raise BadRequestError(
                f"plan_config.tranches[{i}] contains unknown keys: {extra}"
            )

    # -- sum(amount_cents) == product.package_size * price_per_unit_cents --
    total_amount = sum(t["amount_cents"] for t in tranches)
    expected_total = product_units * price_per_unit_cents
    if total_amount != expected_total:
        raise BadRequestError(
            f"plan_config total amount ({total_amount}) does not match "
            f"product price ({product_units} units × {price_per_unit_cents} = {expected_total})"
        )

    # -- sum(units_percent) == 100 --
    total_pct = sum(t["units_percent"] for t in tranches)
    if total_pct != 100:
        raise BadRequestError(
            f"plan_config total units_percent ({total_pct}) must equal 100"
        )

    # -- Sprint 6.2: units_unlocked must decompose exactly --
    # Each tranche unlocks: units_percent * product.package_size // 100
    # The sum of all unlocked units must equal product.package_size exactly.
    # This prevents rounding errors when tranches are expanded into
    # InstallmentTranche records with integer units_unlocked values.
    total_unlocked = sum(
        t["units_percent"] * product_units // 100 for t in tranches
    )
    if total_unlocked != product_units:
        raise BadRequestError(
            f"plan_config units decomposition error: "
            f"sum(units_percent * {product_units} // 100) = {total_unlocked}, "
            f"expected {product_units}. "
            f"Adjust units_percent values to produce exact integer units per tranche"
        )

    # -- bonus_units --
    bonus_units = config.get("bonus_units")
    if bonus_units is None:
        raise BadRequestError("plan_config.bonus_units is required")
    if not isinstance(bonus_units, int) or bonus_units < 0:
        raise BadRequestError(
            "plan_config.bonus_units must be a non-negative integer"
        )

    # -- agent_bonus_units --
    agent_bonus_units = config.get("agent_bonus_units")
    if agent_bonus_units is None:
        raise BadRequestError("plan_config.agent_bonus_units is required")
    if not isinstance(agent_bonus_units, int) or agent_bonus_units < 0:
        raise BadRequestError(
            "plan_config.agent_bonus_units must be a non-negative integer"
        )

    # -- Reject unknown keys --
    allowed_keys = {"tranches", "bonus_units", "agent_bonus_units"}
    extra_keys = set(config.keys()) - allowed_keys
    if extra_keys:
        raise BadRequestError(
            f"plan_config contains unknown keys: {extra_keys}"
        )
