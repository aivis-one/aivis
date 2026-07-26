# =============================================================================
# AIVIS.ONE Backend -- Processor Registry (Sprint 6.1, Sprint 7.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Orchestrates which processors run for a given purchase.
#   Sprint 6.1: PurchaseProcessor + GiftProcessor.
#   Sprint 7.2: + ReferralProcessor.
#   Sprint 7.3: + VolumeProcessor.
#
# USAGE:
#   registry = ProcessorRegistry(investor_portfolio_cents=50000)
#   transactions = registry.run_all(context)
#   # -> flat list of Transaction from all processors
#
# ORDER:
#   1. PurchaseProcessor (always runs -- core sale)
#   2. GiftProcessor (runs if bonuses configured)
#   3. ReferralProcessor (Sprint 7.2 -- runs if agent_chain non-empty)
#   4. VolumeProcessor (Sprint 7.3 -- cron-triggered, not per-purchase)
# =============================================================================

from app.modules.processors.base import PurchaseContext, Transaction
from app.modules.processors.gift import GiftProcessor
from app.modules.processors.purchase import PurchaseProcessor
from app.modules.processors.referral import ReferralProcessor


class ProcessorRegistry:
    """Run all applicable processors for a purchase context."""

    def __init__(self, *, investor_portfolio_cents: int = 0) -> None:
        self._purchase = PurchaseProcessor()
        self._gift = GiftProcessor(
            investor_portfolio_cents=investor_portfolio_cents,
        )
        self._referral = ReferralProcessor()

    def run_all(self, context: PurchaseContext) -> list[Transaction]:
        """Execute all processors and return combined transactions.

        Validates SUM=0 invariant for each transaction.

        Raises:
            ValueError: If any transaction violates SUM=0 invariant.
        """
        transactions: list[Transaction] = []

        # 1. Core sale distribution.
        transactions.extend(self._purchase.process(context))

        # 2. Gift bonuses (if configured).
        if context.purchase_config_bonuses:
            transactions.extend(self._gift.process(context))

        # 3. Referral commissions (Sprint 7.2).
        if context.agent_chain:
            transactions.extend(self._referral.process(context))

        # Validate invariant.
        for txn in transactions:
            entry_sum = sum(e.amount_cents for e in txn.entries)
            if entry_sum != 0:
                raise ValueError(
                    f"Transaction invariant violated: "
                    f"SUM(entries) = {entry_sum} != 0 "
                    f"(reason={txn.reason!r})"
                )

        return transactions
