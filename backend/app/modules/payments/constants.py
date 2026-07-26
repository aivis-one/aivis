# =============================================================================
# AIVIS.ONE Backend -- Payment Constants (Sprint 5.2)
# =============================================================================
#
# ENUMS:
#   PaymentType   -- crypto | bank
#   PaymentStatus -- created | frozen | confirmed | failed | reversed
#
# STATE MACHINE (from AIVIS-State-Machines.md section 1):
#   created   -> frozen    (webhook: provider confirmed receipt)
#   created   -> failed    (webhook: rejected / daemon: expires_at <= now())
#   frozen    -> confirmed (daemon: frozen_until <= now())
#   frozen    -> reversed  (Staff: chargeback during cooling-off)
#   confirmed -> reversed  (Staff: fraud dispute after confirmation)
#
# Terminal statuses: failed, reversed (no exit possible).
#
# RULE: All columns use String (not SAEnum) to avoid PostgreSQL type
# conflicts in migrations.
# =============================================================================

import enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PaymentType(enum.StrEnum):
    """Payment method type."""

    CRYPTO = "crypto"
    BANK = "bank"


class PaymentStatus(enum.StrEnum):
    """Payment lifecycle status."""

    CREATED = "created"
    FROZEN = "frozen"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REVERSED = "reversed"


# ---------------------------------------------------------------------------
# State machine transitions
# ---------------------------------------------------------------------------

VALID_PAYMENT_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentStatus.CREATED: frozenset({PaymentStatus.FROZEN, PaymentStatus.FAILED}),
    PaymentStatus.FROZEN: frozenset({PaymentStatus.CONFIRMED, PaymentStatus.REVERSED}),
    PaymentStatus.CONFIRMED: frozenset({PaymentStatus.REVERSED}),
    # Terminal statuses -- no transitions out.
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REVERSED: frozenset(),
}


def validate_payment_status_transition(
    current: str,
    new: str,
) -> None:
    """Validate that a payment status transition is allowed.

    Raises:
        BadRequestError: If transition is not in the state machine.
    """
    from app.core.exceptions import BadRequestError

    allowed = VALID_PAYMENT_STATUS_TRANSITIONS.get(current, frozenset())
    if new not in allowed:
        raise BadRequestError(
            f"Cannot transition payment from '{current}' to '{new}'"
        )
