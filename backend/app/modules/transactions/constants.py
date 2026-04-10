# =============================================================================
# CBSHOME Backend -- Transaction Constants (Sprint 6.4)
# =============================================================================
#
# Transaction is an immutable event log. Each row = one fact.
# Type format: "{entity}:{event}" -- filter by prefix for lifecycle.
#
# TYPES:
#   deposit:received           -- crypto webhook received, frozen
#   deposit:confirmed          -- daemon confirmed deposit
#   deposit:reversed           -- chargeback on deposit
#   purchase:completed         -- instant purchase executed
#   purchase:gift              -- bonus units allocated
#   installment:tranche_paid   -- installment tranche paid
#   installment:completed      -- plan closed, bonuses issued
#   installment:defaulted      -- plan defaulted after overdue
#   withdrawal:created         -- withdrawal request submitted
#   withdrawal:confirmed       -- staff approved withdrawal
#   withdrawal:rejected        -- staff declined withdrawal
#   withdrawal:completed       -- payout succeeded
#   withdrawal:failed          -- payout failed
#   reversal:completed         -- chargeback reversal executed
#
# REFERENCE TYPES:
#   payment, purchase, withdrawal, installment_plan
# =============================================================================

import enum


class TransactionType(enum.StrEnum):
    """Immutable event types for the transaction log."""

    # Deposits
    DEPOSIT_RECEIVED = "deposit:received"
    DEPOSIT_CONFIRMED = "deposit:confirmed"
    DEPOSIT_REVERSED = "deposit:reversed"

    # Purchases
    PURCHASE_COMPLETED = "purchase:completed"
    PURCHASE_GIFT = "purchase:gift"

    # Installments
    INSTALLMENT_TRANCHE_PAID = "installment:tranche_paid"
    INSTALLMENT_COMPLETED = "installment:completed"
    INSTALLMENT_DEFAULTED = "installment:defaulted"

    # Withdrawals
    WITHDRAWAL_CREATED = "withdrawal:created"
    WITHDRAWAL_CONFIRMED = "withdrawal:confirmed"
    WITHDRAWAL_REJECTED = "withdrawal:rejected"
    WITHDRAWAL_COMPLETED = "withdrawal:completed"
    WITHDRAWAL_FAILED = "withdrawal:failed"

    # Reversals
    REVERSAL_COMPLETED = "reversal:completed"


class ReferenceType(enum.StrEnum):
    """Type of the referenced entity in transaction log."""

    PAYMENT = "payment"
    PURCHASE = "purchase"
    WITHDRAWAL = "withdrawal"
    INSTALLMENT_PLAN = "installment_plan"
