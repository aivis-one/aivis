# =============================================================================
# CBSHOME Backend -- Canonical Constants
# =============================================================================
#
# SHARED CONSTANTS:
#   USER_AGENT_MAX_LEN -- max user_agent length stored in DB (AuditLog,
#                         DocumentSigning) and truncated in middleware.
#                         Prevents disk exhaustion via oversized headers.
#                         TD-020: consolidated from middleware.py + audit.py.
#
# LEDGER REASONS:
#   All ledger entry `reason` strings must come from this registry.
#   Format: "{operation}:{details}"
#
# RULES:
#   - reason.split(":")[0]  ->  operation type (for semaphore filtering)
#   - Reversal entries:     original_reason + ":reversal" suffix
#   - Semaphores filter by prefix, e.g. "deposit:", "commission:"
#
# USAGE:
#   from app.core.constants import LedgerReason, USER_AGENT_MAX_LEN
#   reason = LedgerReason.DEPOSIT_CRYPTO.format(tx_hash=tx_hash)
#
# SOURCE OF TRUTH: CBSHOME-Financial-System.md section 6
# =============================================================================

# Max length for user_agent strings stored in DB and structlog context.
# Used in: TraceIdMiddleware, record_audit(), DocumentSigning.
USER_AGENT_MAX_LEN: int = 500


class LedgerReason:
    """Canonical ledger reason string templates.

    String constants with {placeholders} for dynamic values.
    Use .format(**kwargs) to fill in values before writing to DB.

    Example:
        reason = LedgerReason.DEPOSIT_CRYPTO.format(tx_hash="0xabc...")
        reason = LedgerReason.COMMISSION_L1.format(
            agent_id=str(agent_id), purchase_id=str(purchase_id)
        )
    """

    # ------------------------------------------------------------------
    # Deposits (active_ledger: +amount)
    # ------------------------------------------------------------------
    DEPOSIT_CRYPTO: str = "deposit:crypto:{tx_hash}"
    DEPOSIT_BANK: str = "deposit:bank:{payment_id}"

    # ------------------------------------------------------------------
    # Purchases (active_ledger: -amount)
    # ------------------------------------------------------------------
    PURCHASE: str = "purchase:{purchase_id}"

    # ------------------------------------------------------------------
    # Gifts -- all free unit allocations (passive_ledger: +0 entries)
    # type: bundle_bonus | airdrop | welcome | campaign |
    #        installment_tranche | installment_completion |
    #        installment_completion_agent
    # ------------------------------------------------------------------
    GIFT: str = "gift:{type}:{reference_id}"

    # ------------------------------------------------------------------
    # Distribution saga (passive_ledger: +amount per recipient)
    # Called by PurchaseProcessor for each purchase/tranche
    # ------------------------------------------------------------------
    DISTRIBUTION_COMPANY: str = "distribution:company:{company_id}:{purchase_id}"
    COMMISSION_L1: str = "commission:l1:{agent_id}:{purchase_id}"
    COMMISSION_L2: str = "commission:l2:{agent_id}:{purchase_id}"
    COMMISSION_L3: str = "commission:l3:{agent_id}:{purchase_id}"
    PLATFORM_REMAINDER: str = "platform:remainder:{purchase_id}"

    # ------------------------------------------------------------------
    # Bonuses
    # ------------------------------------------------------------------
    BONUS_REFERRAL: str = "bonus:referral:{referral_id}:{purchase_id}"
    BONUS_VOLUME: str = "bonus:volume:{period}:{agent_id}"
    BONUS_PROMO: str = "bonus:promo:{promo_code}:{purchase_id}"

    # ------------------------------------------------------------------
    # Installments
    # ------------------------------------------------------------------
    INSTALLMENT_TRANCHE: str = "installment:tranche:{tranche_id}"

    # ------------------------------------------------------------------
    # Withdrawals (passive_ledger: -amount)
    # ------------------------------------------------------------------
    WITHDRAWAL: str = "withdrawal:{withdrawal_id}"

    # ------------------------------------------------------------------
    # Refunds
    # ------------------------------------------------------------------
    REFUND: str = "refund:{purchase_id}"

    # ------------------------------------------------------------------
    # Internal transfers
    # ------------------------------------------------------------------
    TRANSFER_INTERNAL: str = "transfer:internal:{from_ledger}:{to_ledger}"

    # ------------------------------------------------------------------
    # Reversals
    # Suffix appended to the original reason string.
    # Example: "deposit:crypto:0xabc:reversal"
    # ------------------------------------------------------------------
    REVERSAL_SUFFIX: str = ":reversal"

    @staticmethod
    def is_reversal(reason: str) -> bool:
        """Check whether a reason string represents a reversal entry."""
        return reason.endswith(LedgerReason.REVERSAL_SUFFIX)

    @staticmethod
    def operation_type(reason: str) -> str:
        """Extract the operation prefix for semaphore filtering.

        Example: "commission:l1:uuid:uuid" -> "commission"
        """
        return reason.split(":")[0]
