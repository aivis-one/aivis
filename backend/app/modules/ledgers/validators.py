# =============================================================================
# CBSHOME Backend -- Ledger Validators (Sprint 5.1)
# =============================================================================
#
# STANDALONE AML ROUTE VALIDATION:
#   validate_route() checks if a source -> target ledger transfer
#   is permitted by the AML matrix.
#
# NOT called inside record_active_ledger() or record_passive_ledger().
# Those are pure write functions that don't know the transfer context.
#
# Called by orchestrator layer:
#   - Transfer service (Phase 6+) for user-initiated transfers
#   - Any endpoint where a user requests inter-ledger movement
#
# Purchase saga does NOT call validate_route() -- it's a controlled
# system operation that legitimately writes active -> passive.
#
# AML MATRIX (from CBSHOME-Financial-System.md section 3):
#   Active  -> Active   ALLOWED
#   Active  -> Passive  FORBIDDEN (layering / mixing)
#   Passive -> Active   ALLOWED
#   Passive -> Passive  ALLOWED
#
# The only forbidden route: Active -> Passive (any user combination).
# =============================================================================

from app.core.exceptions import AMLViolationError


def validate_route(source: str, target: str) -> None:
    """Validate that a ledger transfer route is AML-compliant.

    Args:
        source: Source ledger type ("active" or "passive").
        target: Target ledger type ("active" or "passive").

    Raises:
        AMLViolationError: If route is Active -> Passive.
    """
    if source == "active" and target == "passive":
        raise AMLViolationError(
            "Active -> Passive route is forbidden by AML policy"
        )
