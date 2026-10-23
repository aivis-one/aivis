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
#   "purchase_amount_gte" -- the amount of this purchase alone >= threshold
#                            (the portfolio does not count)
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


def bonus_condition_met(
    bonus: dict, amount_cents: int, portfolio_cents: int
) -> bool:
    """Check whether one bonus condition holds for a purchase.

    Shared by the purchase (GiftProcessor) and the pre-payment bonus
    preview so both always apply the same rule.
    """
    condition = bonus.get("condition", "always")

    if condition == "always":
        return True

    if condition == "portfolio_size_gte":
        threshold = bonus.get("threshold_cents", 0)
        # Portfolio includes current purchase.
        return portfolio_cents + amount_cents >= threshold

    if condition == "purchase_amount_gte":
        # This purchase alone, not the portfolio.
        return amount_cents >= bonus.get("threshold_cents", 0)

    # Unknown condition -- skip (defensive).
    return False


def bonus_units_for(bonus: dict, units: int) -> int:
    """Bonus units of one bonus: floor(units * percent / 100)."""
    pct = bonus.get("bonus_units_percent", 0)
    if pct <= 0:
        return 0
    return math.floor(units * pct / 100)


def total_bonus_units(
    bonuses: list[dict],
    units: int,
    amount_cents: int,
    portfolio_cents: int,
) -> tuple[int, float]:
    """Sum the bonuses a purchase triggers.

    Returns (bonus_units, bonus_percent): the total units across every
    bonus whose condition holds and that yields at least one unit, and
    the sum of those bonuses' percentages.
    """
    total_units = 0
    total_percent = 0.0
    for bonus in bonuses or []:
        if not bonus_condition_met(bonus, amount_cents, portfolio_cents):
            continue
        b_units = bonus_units_for(bonus, units)
        if b_units <= 0:
            continue
        total_units += b_units
        total_percent += float(bonus.get("bonus_units_percent", 0))
    return total_units, total_percent


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
        return bonus_condition_met(
            bonus, context.amount_cents, self._portfolio_cents
        )

    def _calc_bonus_units(
        self, bonus: dict, context: PurchaseContext
    ) -> int:
        """Calculate bonus units from percentage."""
        return bonus_units_for(bonus, context.units)
