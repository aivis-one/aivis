# =============================================================================
# AIVIS.ONE Backend -- Canonical Constants
# =============================================================================
#
# SHARED CONSTANTS:
#   USER_AGENT_MAX_LEN -- max user_agent length stored in DB (AuditLog,
#                         DocumentSigning) and truncated in middleware.
#                         Prevents disk exhaustion via oversized headers.
#                         TD-020: consolidated from middleware.py + audit.py.
#
# STAFF PERMISSIONS:
#   Single source of truth in app/modules/staff/constants.py.
#   Not duplicated here.
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
# SOURCE OF TRUTH: AIVIS-Financial-System.md section 6
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
        reason = LedgerReason.COMMISSION.format(
            level=1, agent_id=str(agent_id), purchase_id=str(purchase_id)
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
    # Installments (active_ledger: -amount, one per tranche payment)
    # ------------------------------------------------------------------
    INSTALLMENT_TRANCHE: str = "installment:tranche:{tranche_id}"

    # ------------------------------------------------------------------
    # Gifts -- all free unit allocations (passive_ledger: +0 entries)
    # type: bundle_bonus | airdrop | welcome | campaign |
    #        installment_tranche | installment_completion |
    #        installment_completion_agent
    # ------------------------------------------------------------------
    GIFT: str = "gift:{type}:{reference_id}"

    # ------------------------------------------------------------------
    # Distribution saga (passive_ledger: movement from platform)
    # ------------------------------------------------------------------
    SAGA_COMPANY_REVENUE: str = "saga:company_revenue:{purchase_id}"
    SAGA_PLATFORM_FEE: str = "saga:platform_fee:{purchase_id}"

    # Sprint 6.1: distribution entries created by PurchaseProcessor.
    DISTRIBUTION_COMPANY: str = "distribution:company:{company_id}:{purchase_id}"
    PLATFORM_REMAINDER: str = "platform:remainder:{purchase_id}"

    # ------------------------------------------------------------------
    # Commissions (passive_ledger: +amount for agent)
    # Sprint 7.2: parametric -- level is 1-based index (L1, L2, L3, ...).
    # Supports arbitrary depth via len(agent_levels) in distribution_config.
    # ------------------------------------------------------------------
    COMMISSION: str = "commission:l{level}:{agent_id}:{purchase_id}"

    # ------------------------------------------------------------------
    # Volume Bonuses (passive_ledger: +amount for agent)
    # Sprint 7.3: monthly/quarterly bonus pool distribution.
    # ------------------------------------------------------------------
    VOLUME_BONUS_MONTHLY: str = "volume_bonus:monthly:{payout_id}"
    VOLUME_BONUS_QUARTERLY: str = "volume_bonus:quarterly:{payout_id}"

    # ------------------------------------------------------------------
    # Transfers (inter-ledger / inter-user)
    # ------------------------------------------------------------------
    TRANSFER_OUT: str = "transfer:out:{transfer_id}"
    TRANSFER_IN: str = "transfer:in:{transfer_id}"

    # ------------------------------------------------------------------
    # Withdrawals (passive_ledger: -amount)
    # ------------------------------------------------------------------
    WITHDRAWAL: str = "withdrawal:{withdrawal_id}"

    # ------------------------------------------------------------------
    # Chargebacks / Reversals
    # ------------------------------------------------------------------
    CHARGEBACK: str = "chargeback:{payment_id}"
    REVERSAL_SUFFIX: str = ":reversal"
