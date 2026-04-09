# =============================================================================
# CBSHOME Backend -- Purchase Constants (Sprint 6.1)
# =============================================================================
#
# PURCHASE STATUS:
#   active   -- normal purchase record
#   reversed -- chargeback processed, mirror entries created
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


class PurchaseLegalBasis(enum.StrEnum):
    """Legal basis for a purchase record."""

    SALE = "sale"
    GIFT = "gift"
    INSTALLMENT_TRANCHE = "installment_tranche"
