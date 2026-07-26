# =============================================================================
# AIVIS.ONE Backend -- Installment Calculator (Sprint 4.3 / B4)
# =============================================================================
#
# Computes a `plan_config` for a Product given staff-chosen tranche
# shape: number of tranches, options skew toward the last tranche, and
# money rounding step. Output is the same shape that
# validate_plan_config() (constants.py) accepts -- staff can submit it
# verbatim to POST /staff/products/{id}/installments to create a real
# InstallmentPlan template.
#
# ALGORITHM (spec §3.9):
#
#   Inputs:
#     package_size           -- Product.package_size
#     price_per_unit_cents   -- Product.price_per_unit_cents
#     num_tranches (N)       -- one of ALLOWED_TRANCHES
#     last_tranche_percent   -- staff-chosen target skew, 30..50
#     amount_rounding_cents  -- one of ALLOWED_AMOUNT_ROUNDINGS
#
#   Percentages:
#     The (N-1) regular tranches share (100 - last_tranche_percent)%
#     equally via integer division. Whatever remainder integer division
#     leaves spills into the last tranche, so the *actual* last-tranche
#     percent may be slightly higher than the requested one. By
#     construction sum(percent) = 100, exactly.
#
#         regular_pct       = (100 - last_tranche_percent) // (N - 1)
#         actual_last_pct   = 100 - regular_pct * (N - 1)
#
#   Units:
#     Each percent rendered as integer options:
#         regular_units     = regular_pct * package_size // 100
#         last_units        = actual_last_pct * package_size // 100
#
#     The units decomposition invariant
#         regular_units * (N - 1) + last_units == package_size
#     must hold (validate_plan_config enforces it). For real-world
#     package sizes (multiples of 100) this is automatic; for awkward
#     sizes the calculator returns 400 with a hint to choose a friendlier
#     package_size.
#
#   Amounts:
#     Regular tranches are rounded DOWN to a multiple of
#     amount_rounding_cents; the last tranche absorbs the rounding
#     remainder, so sum(amount_cents) = package_size * price exactly.
#
#         total                = package_size * price_per_unit_cents
#         regular_amount_cents = (total // N // rounding) * rounding
#         last_amount_cents    = total - regular_amount_cents * (N - 1)
#
# ERRORS (BadRequestError):
#   - num_tranches / amount_rounding_cents outside the allowed sets
#     (defensive; the request schema rejects these too)
#   - last_tranche_percent outside [LAST_TRANCHE_PERCENT_MIN,
#     LAST_TRANCHE_PERCENT_MAX]
#   - regular_pct = 0 (input last_tranche_percent too high for N)
#   - units decomposition fails (package_size too awkward)
#   - regular_amount_cents = 0 (rounding step too coarse)
#   - last_amount_cents <= 0 (regular tranches eat the whole pot)
#
# DESIGN NOTES:
#   - Pure function. No DB access. Caller (router) loads the Product
#     and passes package_size + price_per_unit_cents. Easier to unit-
#     test, easier to reuse from a future seed/preview script.
#   - Output shape mirrors validate_plan_config(): staff UI can
#     immediately PATCH bonus_units / agent_bonus_units (calculator
#     leaves them at 0) and POST to the installment-create endpoint
#     without any field renaming.
# =============================================================================

from app.core.exceptions import BadRequestError
from app.modules.products.constants import (
    ALLOWED_AMOUNT_ROUNDINGS,
    ALLOWED_TRANCHES,
    LAST_TRANCHE_PERCENT_MAX,
    LAST_TRANCHE_PERCENT_MIN,
)


def calculate_installment_preview(
    *,
    package_size: int,
    price_per_unit_cents: int,
    num_tranches: int,
    last_tranche_percent: int,
    amount_rounding_cents: int,
) -> dict:  # type: ignore[type-arg]
    """Compute plan_config + summary from staff inputs.

    All arguments are keyword-only -- swapping num_tranches with
    last_tranche_percent silently would be too easy otherwise.

    Returns:
        {
            "plan_config": {
                "tranches": [
                    {"amount_cents": int, "units_percent": int},
                    ...
                ],
                "bonus_units": 0,
                "agent_bonus_units": 0,
            },
            "summary": {
                "total_amount_cents": int,
                "package_size": int,
                "num_tranches": int,
                "regular_amount_cents": int,
                "last_amount_cents": int,
                "regular_units": int,
                "last_units": int,
                "regular_units_percent": int,
                "last_units_percent": int,
            },
        }
    """
    # -- Defensive input checks (router schema covers most of these) --
    if package_size <= 0:
        raise BadRequestError("package_size must be positive")
    if price_per_unit_cents <= 0:
        raise BadRequestError("price_per_unit_cents must be positive")
    if num_tranches not in ALLOWED_TRANCHES:
        raise BadRequestError(
            f"num_tranches must be one of {sorted(ALLOWED_TRANCHES)}"
        )
    if amount_rounding_cents not in ALLOWED_AMOUNT_ROUNDINGS:
        raise BadRequestError(
            f"amount_rounding_cents must be one of "
            f"{sorted(ALLOWED_AMOUNT_ROUNDINGS)}"
        )
    if not (
        LAST_TRANCHE_PERCENT_MIN
        <= last_tranche_percent
        <= LAST_TRANCHE_PERCENT_MAX
    ):
        raise BadRequestError(
            f"last_tranche_percent must be between "
            f"{LAST_TRANCHE_PERCENT_MIN} and {LAST_TRANCHE_PERCENT_MAX}"
        )

    n_regular = num_tranches - 1

    # -- Percent allocation --
    # Regular tranches share (100 - last_tranche_percent)% via integer
    # division; remainder spills into the last tranche.
    regular_pct = (100 - last_tranche_percent) // n_regular
    if regular_pct <= 0:
        # Not reachable with current bounds (LAST_TRANCHE_PERCENT_MAX=50,
        # min num_tranches=3, so (100-50)//2 = 25 > 0). Defensive.
        raise BadRequestError(
            f"last_tranche_percent={last_tranche_percent} too high for "
            f"num_tranches={num_tranches}: regular tranches would round to 0%"
        )
    actual_last_pct = 100 - regular_pct * n_regular

    # -- Units (validate_plan_config invariant must hold) --
    regular_units = regular_pct * package_size // 100
    last_units = actual_last_pct * package_size // 100
    if regular_units * n_regular + last_units != package_size:
        # Awkward package_size for these percentages. Real-world packages
        # are 100/1000/5000/10000 and divide cleanly; reject otherwise
        # rather than ship a config that validate_plan_config will throw on.
        raise BadRequestError(
            f"package_size={package_size} cannot be cleanly distributed "
            f"across {num_tranches} tranches at "
            f"{regular_pct}%/{actual_last_pct}%. Use a package_size "
            f"divisible by 100, or different num_tranches / "
            f"last_tranche_percent."
        )

    # -- Amounts --
    total_amount = package_size * price_per_unit_cents
    regular_amount = (
        total_amount // num_tranches // amount_rounding_cents
    ) * amount_rounding_cents
    if regular_amount <= 0:
        raise BadRequestError(
            f"amount_rounding_cents={amount_rounding_cents} is too coarse "
            f"for total={total_amount} / num_tranches={num_tranches}; "
            f"regular tranche rounds to 0. Use a smaller rounding step."
        )
    last_amount = total_amount - regular_amount * n_regular
    if last_amount <= 0:
        # Regular tranches ate the whole pot. Tighter rounding fixes it.
        raise BadRequestError(
            f"computed last_amount={last_amount} is non-positive. "
            f"Reduce amount_rounding_cents or num_tranches."
        )

    # -- Build plan_config --
    tranches: list[dict] = []  # type: ignore[type-arg]
    for _ in range(n_regular):
        tranches.append({
            "amount_cents": regular_amount,
            "units_percent": regular_pct,
        })
    tranches.append({
        "amount_cents": last_amount,
        "units_percent": actual_last_pct,
    })

    plan_config = {
        "tranches": tranches,
        # Calculator does not invent completion bonuses. Staff edits
        # them in the UI before submitting to /installments if needed.
        "bonus_units": 0,
        "agent_bonus_units": 0,
    }

    summary = {
        "total_amount_cents": total_amount,
        "package_size": package_size,
        "num_tranches": num_tranches,
        "regular_amount_cents": regular_amount,
        "last_amount_cents": last_amount,
        "regular_units": regular_units,
        "last_units": last_units,
        # Surface the actual percent vs the requested one so the UI
        # can show "you asked for 33%, got 35% (rounding)" without
        # recomputing.
        "regular_units_percent": regular_pct,
        "last_units_percent": actual_last_pct,
    }

    return {"plan_config": plan_config, "summary": summary}
