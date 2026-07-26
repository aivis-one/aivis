# =============================================================================
# AIVIS.ONE Backend -- Referral Processor (Sprint 7.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Distribute agent commissions from Platform's passive_ledger.
#   For each agent in agent_chain, move commission from Platform to Agent.
#
# DISTRIBUTION FLOW (per level):
#   1. Platform passive_ledger: -commission_cents
#   2. Agent passive_ledger: +commission_cents
#
# AGENT_LEVELS:
#   distribution_config["agent_levels"] = [0.10, 0.03, 0.01]
#   Arbitrary length. zip(agent_chain, agent_levels) pairs each agent
#   with their commission percentage. Extra levels without agents are
#   skipped (Platform keeps the remainder).
#
# EMPTY CHAIN:
#   agent_chain=[] -> process() returns [] -> no commissions.
#   Platform keeps full remainder. This is the organic purchase path.
#
# ROUNDING:
#   All amounts computed via round(pct * amount_cents). Banker's rounding
#   ensures fair distribution. Any sub-cent remainder stays on Platform.
#
# INVARIANT:
#   Each returned Transaction has SUM(entries) = 0.
#   One Transaction per commission level (easier to reverse individually).
# =============================================================================

from app.core.constants import LedgerReason
from app.modules.processors.base import (
    LedgerEntry,
    PurchaseContext,
    Transaction,
)


class ReferralProcessor:
    """Distribute agent commissions from Platform passive_ledger."""

    def process(self, context: PurchaseContext) -> list[Transaction]:
        """Generate commission transactions for each agent in chain.

        Returns one Transaction per agent level. Empty list if no agents.
        """
        if not context.agent_chain:
            return []

        agent_levels = context.distribution_config.get("agent_levels", [])
        if not agent_levels:
            return []

        amount = context.amount_cents
        pid = "{purchase_id}"
        transactions: list[Transaction] = []

        for level_idx, (agent_id, pct) in enumerate(
            zip(context.agent_chain, agent_levels), start=1
        ):
            commission_cents = round(pct * amount)
            if commission_cents <= 0:
                continue

            reason = LedgerReason.COMMISSION.format(
                level=level_idx,
                agent_id=str(agent_id),
                purchase_id=pid,
            )

            entries = [
                # Debit Platform passive_ledger.
                LedgerEntry(
                    user_id=context.platform_user_id,
                    ledger_type="passive",
                    amount_cents=-commission_cents,
                    reason=reason,
                    origin_payment_id=context.origin_payment_id,
                    frozen_until=context.frozen_until,
                ),
                # Credit Agent passive_ledger.
                LedgerEntry(
                    user_id=agent_id,
                    ledger_type="passive",
                    amount_cents=commission_cents,
                    reason=reason,
                    origin_payment_id=context.origin_payment_id,
                    frozen_until=context.frozen_until,
                ),
            ]

            transactions.append(Transaction(
                reason=reason,
                legal_basis="sale",
                entries=entries,
                units=0,
            ))

        return transactions
