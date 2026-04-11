# =============================================================================
# CBSHOME Backend -- Volume Processor (Sprint 7.3)
# =============================================================================
#
# RESPONSIBILITY:
#   Distribute a volume bonus pool among ranked agents proportionally
#   by their sales volume. Pure synchronous logic, no I/O.
#
# NOT registered in ProcessorRegistry -- triggered by cron worker,
# not per-purchase. Called from commissions/worker.py.
#
# DISTRIBUTION:
#   Each agent receives: pool_cents * (agent_volume / total_volume).
#   Banker's rounding (round()). Any sub-cent remainder stays on Platform.
#
# INVARIANT:
#   Each returned Transaction has SUM(entries) = 0.
#   One Transaction per agent (easier to reverse individually).
#
# REASON STRING:
#   Uses "{payout_id}" placeholder -- worker replaces with real UUID
#   after creating VolumePayout record.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.constants import LedgerReason
from app.modules.processors.base import LedgerEntry, Transaction


@dataclass(frozen=True)
class AgentRank:
    """Ranked agent data for pool distribution."""

    agent_id: UUID
    rank: int
    volume_cents: int


class VolumeProcessor:
    """Distribute volume bonus pool among ranked agents."""

    def distribute_pool(
        self,
        agents_ranked: list[AgentRank],
        pool_cents: int,
        platform_user_id: UUID,
        period_type: str,
    ) -> list[Transaction]:
        """Split pool proportionally by volume among ranked agents.

        Args:
            agents_ranked: Agents sorted by rank (1-based). Each has volume_cents.
            pool_cents: Total pool to distribute.
            platform_user_id: Platform system user UUID (source of funds).
            period_type: "monthly" or "quarterly" (for reason string).

        Returns:
            List of Transactions. One per agent. Empty if no agents or pool=0.
            Each Transaction: Platform passive -share -> Agent passive +share.
            SUM=0 invariant per transaction.
        """
        if not agents_ranked or pool_cents <= 0:
            return []

        total_volume = sum(a.volume_cents for a in agents_ranked)
        if total_volume <= 0:
            return []

        reason_template = (
            LedgerReason.VOLUME_BONUS_MONTHLY
            if period_type == "monthly"
            else LedgerReason.VOLUME_BONUS_QUARTERLY
        )

        pid = "{payout_id}"
        transactions: list[Transaction] = []

        for agent in agents_ranked:
            share = round(pool_cents * agent.volume_cents / total_volume)
            if share <= 0:
                continue

            reason = reason_template.format(payout_id=pid)

            entries = [
                # Debit Platform passive_ledger.
                LedgerEntry(
                    user_id=platform_user_id,
                    ledger_type="passive",
                    amount_cents=-share,
                    reason=reason,
                    origin_payment_id=None,
                    frozen_until=None,
                ),
                # Credit Agent passive_ledger.
                LedgerEntry(
                    user_id=agent.agent_id,
                    ledger_type="passive",
                    amount_cents=share,
                    reason=reason,
                    origin_payment_id=None,
                    frozen_until=None,
                ),
            ]

            transactions.append(Transaction(
                reason=reason,
                legal_basis="volume_bonus",
                entries=entries,
                units=0,
            ))

        return transactions
