# =============================================================================
# AIVIS.ONE Backend -- Gift Processor (Sprint 6.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Process bonus allocations from purchase_config.bonuses[].
#   Creates zero-amount transactions (legal_basis="gift") for each
#   triggered bonus. Each gift generates a Purchase record with
#   paid_cents=0.
#
# BONUS CONDITIONS:
#   "always"              -- unconditional bonus on every purchase
#   "portfolio_size_gte"  -- investor's total paid_cents >= threshold
#
# FUNDED_BY:
#   "company"  -- bonus units deducted from company's passive_ledger
#   "platform" -- bonus units deducted from platform's passive_ledger
#   In practice, zero-amount entries are created for both sides
#   (semaphore compliance). The funded_by field is recorded in the
#   reason string for audit purposes.
#
# ZERO-AMOUNT ENTRIES:
#   Gift transactions have amount_cents=0 on all entries.
#   This is mandatory: semaphore S-02 requires
#   COUNT(active_ledger) == COUNT(purchases) for every purchase.
#
# PORTFOLIO CALCULATION:
#   Computed from investor's existing Purchase records (SUM paid_cents).
#   Done inline in Sprint 6.1. May be extracted to a helper later.
#
# INVARIANT:
#   SUM(entries.amount_cents) == 0 for each returned Transaction.
#   Trivially true since all amounts are 0.
# =============================================================================

import math

from app.core.constants import LedgerReason
from app.modules.processors.base import (
    LedgerEntry,
    PurchaseContext,
    Transaction,
)


class GiftProcessor:
    """Process bonus allocations from purchase_config.bonuses[]."""

    def __init__(self, investor_portfolio_cents: int = 0) -> None:
        """Initialize with investor's current portfolio size.

        Args:
            investor_portfolio_cents: SUM(paid_cents) from investor's
                existing Purchase records. Passed in by execute_purchase()
                before calling process().
        """
        self._portfolio_cents = investor_portfolio_cents

    def process(self, context: PurchaseContext) -> list[Transaction]:
        """Generate gift transactions for triggered bonuses.

        Returns one Transaction per triggered bonus, each with
        legal_basis="gift" and zero-amount entries.
        """
        bonuses = context.purchase_config_bonuses
        if not bonuses:
            return []

        transactions: list[Transaction] = []

        for bonus in bonuses:
            if not self._condition_met(bonus, context):
                continue

            bonus_units = self._calc_bonus_units(bonus, context)
            if bonus_units <= 0:
                continue

            funded_by = bonus.get("funded_by", "company")
            bonus_type = bonus.get("condition", "always")
            pid = "{purchase_id}"

            reason = LedgerReason.GIFT.format(
                type=f"bonus:{bonus_type}:{funded_by}",
                reference_id=pid,
            )

            # Zero-amount entries for semaphore compliance.
            # Investor gets a zero active_ledger entry.
            # Funder (company or platform) gets a zero passive_ledger entry.
            funder_id = (
                context.company_user_id
                if funded_by == "company"
                else context.platform_user_id
            )

            entries = [
                LedgerEntry(
                    user_id=context.investor_id,
                    ledger_type="active",
                    amount_cents=0,
                    reason=reason,
                    origin_payment_id=context.origin_payment_id,
                    frozen_until=context.frozen_until,
                ),
                LedgerEntry(
                    user_id=funder_id,
                    ledger_type="passive",
                    amount_cents=0,
                    reason=reason,
                    origin_payment_id=context.origin_payment_id,
                    frozen_until=context.frozen_until,
                ),
            ]

            transactions.append(Transaction(
                reason=reason,
                legal_basis="gift",
                entries=entries,
                units=bonus_units,
            ))

        return transactions

    def _condition_met(
        self, bonus: dict, context: PurchaseContext
    ) -> bool:
        """Check if bonus condition is satisfied."""
        condition = bonus.get("condition", "always")

        if condition == "always":
            return True

        if condition == "portfolio_size_gte":
            threshold = bonus.get("threshold_cents", 0)
            # Portfolio includes current purchase.
            total = self._portfolio_cents + context.amount_cents
            return total >= threshold

        # Unknown condition -- skip (defensive).
        return False

    def _calc_bonus_units(
        self, bonus: dict, context: PurchaseContext
    ) -> int:
        """Calculate bonus units from percentage."""
        pct = bonus.get("bonus_units_percent", 0)
        if pct <= 0:
            return 0
        return math.floor(context.units * pct / 100)
