# =============================================================================
# AIVIS.ONE Backend -- Payment Constants (Sprint 5.2)
# =============================================================================
#
# ENUMS:
#   PaymentType         -- crypto | bank
#   PaymentStatus       -- created | frozen | confirmed | failed | reversed
#   ServiceEventStatus  -- the four statuses the payments service emits
#                          webhook events for (H8)
#   WebhookOutcome      -- what an accepted event caused here (H8)
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


class ServiceEventStatus(enum.StrEnum):
    """The four statuses the payments service emits events for.

    THE SERVICE HAS SIX INVOICE STATUSES AND EMITS EVENTS FOR FOUR:
    `created` and `awaiting_confirmations` are not terminal and produce
    no event (TOR section 8). Listing only the four here keeps the
    receiver's schema honest about what can actually arrive.

    Only CONFIRMED credits. The other three are still processed rather
    than ignored -- a non-2xx answer would make the service retry them
    until its outbox row goes `failed`, which is irreversible.
    """

    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    STALLED = "stalled"


class WebhookOutcome(enum.StrEnum):
    """What an accepted event actually caused on our side.

    Stored on the event row so that "did this payment land, and if not
    why" is one SELECT rather than a search through logs.
    """

    # confirmed, with a credited amount: Payment + ledger written.
    CREDITED = "credited"
    # A non-crediting status: the invoice's cached status was refreshed
    # and nothing else happened.
    STATUS_CACHED = "status_cached"
    # The product_ref resolves to no local invoice row. Accepted (200)
    # rather than retried: no retry can make the row appear, and the
    # attempts spent would end with the service's outbox row in
    # `failed` for an event nobody could ever have processed.
    NO_INVOICE = "no_invoice"


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
