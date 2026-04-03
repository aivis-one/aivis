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
# STAFF PERMISSIONS (Sprint 3.1):
#   VALID_STAFF_PERMISSIONS -- frozenset of all known permission keys.
#   DEFAULT_STAFF_PERMISSIONS -- default values applied when StaffProfile
#                                does not override a key.
#   Resolution: profile.permissions[key] ?? DEFAULT_STAFF_PERMISSIONS[key]
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


# ---------------------------------------------------------------------------
# Staff Permissions (Sprint 3.1)
# ---------------------------------------------------------------------------

# All recognised permission keys. Used as dev guard in require_staff_permission
# and in update_permissions validation.
VALID_STAFF_PERMISSIONS: frozenset[str] = frozenset({
    "avatar_mode",
    "kyc_approve",
    "payment_review",
    "user_block",
    "financial_operations",
    "agent_application_review",
    "translation_edit",
})

# Default permission values applied when StaffProfile.permissions
# does not contain the key. "Admin" = all defaults. "Support" =
# override financial_operations -> false (etc.) in StaffProfile.
DEFAULT_STAFF_PERMISSIONS: dict[str, bool] = {
    "avatar_mode": True,
    "kyc_approve": True,
    "payment_review": True,
    "user_block": True,
    "financial_operations": True,
    "agent_application_review": True,
    "translation_edit": False,
}


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
    # Saga distribution (passive_ledger: +amount per recipient)
    # ------------------------------------------------------------------
    SAGA_COMPANY_REVENUE: str = "saga:company_revenue:{purchase_id}"
    SAGA_PLATFORM_FEE: str = "saga:platform_fee:{purchase_id}"

    # ------------------------------------------------------------------
    # Commissions (passive_ledger: +amount for agent)
    # ------------------------------------------------------------------
    COMMISSION_L1: str = "commission:l1:{agent_id}:{purchase_id}"
    COMMISSION_L2: str = "commission:l2:{agent_id}:{purchase_id}"
    COMMISSION_L3: str = "commission:l3:{agent_id}:{purchase_id}"

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
