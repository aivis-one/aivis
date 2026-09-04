# =============================================================================
# AIVIS.ONE Backend -- Transaction Constants (Sprint 6.4)
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
#   purchase:reversed          -- purchase unwound by chargeback (R-2.2)
#   installment:tranche_paid   -- installment tranche paid
#   installment:completed      -- plan closed, bonuses issued
#   installment:defaulted      -- plan defaulted after overdue
#   withdrawal:created         -- withdrawal request submitted
#   withdrawal:confirmed       -- staff approved withdrawal
#   withdrawal:rejected        -- staff declined withdrawal
#   withdrawal:completed       -- payout succeeded
#   withdrawal:failed          -- payout failed
#   reversal:completed         -- chargeback reversal executed
#   kyc:verification_fee       -- KYC verification session paid for
#
# REFERENCE TYPES:
#   payment, purchase, withdrawal, installment_plan, kyc_application
#
# EXPORT (TASK-39 item 2):
#   EXPORT_MAX_ROWS -- hard cap on rows a single CSV export may contain.
#   list_transactions() is paginated for the screen (<=100/page); an
#   export has no page control on the client, so an unfiltered history
#   for a very active account could otherwise mean an unbounded query
#   and an unbounded in-memory CSV. The service layer counts matching
#   rows FIRST (list_transactions's separate COUNT query, unaffected by
#   LIMIT) and refuses the export with a 400 if the count exceeds this
#   cap, naming the actual count so the user knows to narrow date_from/
#   date_to or the type filter and retry -- never a silent truncation.
#   5000 rows is generous for a personal statement (years of activity
#   for an active investor) while keeping one export's CSV comfortably
#   in the low hundreds of KB.
# =============================================================================

import enum

EXPORT_MAX_ROWS = 5000


class TransactionType(enum.StrEnum):
    """Immutable event types for the transaction log."""

    # Deposits
    DEPOSIT_RECEIVED = "deposit:received"
    DEPOSIT_CONFIRMED = "deposit:confirmed"
    DEPOSIT_REVERSED = "deposit:reversed"

    # Purchases
    PURCHASE_COMPLETED = "purchase:completed"
    PURCHASE_GIFT = "purchase:gift"
    PURCHASE_REVERSED = "purchase:reversed"

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

    # KYC (H10)
    # ONE TYPE, NOT A PAIR. The fee buys a verification session, and the
    # money is gone whatever the session decides -- that is the point of
    # charging before verifying rather than after. There is no refund
    # event to log, so no second type describes one.
    KYC_VERIFICATION_FEE = "kyc:verification_fee"


class ReferenceType(enum.StrEnum):
    """Type of the referenced entity in transaction log."""

    PAYMENT = "payment"
    PURCHASE = "purchase"
    WITHDRAWAL = "withdrawal"
    INSTALLMENT_PLAN = "installment_plan"
    # The application the fee bought (H10). reference_id is its UUID.
    # NULL was the cheaper option -- the constraint allows it -- and was
    # rejected: without the link, "I paid and was refused" cannot be
    # answered from the transaction log alone.
    KYC_APPLICATION = "kyc_application"
