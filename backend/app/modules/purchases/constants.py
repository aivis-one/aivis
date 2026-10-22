# =============================================================================
# AIVIS.ONE Backend -- Purchase Constants (Sprint 6.1)
# =============================================================================
#
# PURCHASE STATUS:
#   active   -- normal purchase record
#   reversed -- chargeback processed, mirror entries created
#   pending_acceptance -- a gift granted by staff that the recipient has not
#                         accepted yet. Credits nothing: no ledger
#                         entry, no pool consumption, not in any portfolio
#                         figure until it becomes active.
#   cancelled -- a pending gift that staff closed before the recipient
#                accepted it. Credits nothing, has no ledger entry, and is
#                not a reversal of real money.
#
# LEGAL BASIS:
#   sale                -- paid purchase (units * price)
#   gift                -- free allocation (paid_cents=0)
#   installment_tranche -- single tranche payment (Sprint 6.2)
# =============================================================================

import enum


class PurchaseStatus(enum.StrEnum):
    """Purchase lifecycle status."""

    ACTIVE = "active"
    REVERSED = "reversed"
    PENDING_ACCEPTANCE = "pending_acceptance"
    CANCELLED = "cancelled"


class PurchaseLegalBasis(enum.StrEnum):
    """Legal basis for a purchase record."""

    SALE = "sale"
    GIFT = "gift"
    INSTALLMENT_TRANCHE = "installment_tranche"
