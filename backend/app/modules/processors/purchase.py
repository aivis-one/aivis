# =============================================================================
# CBSHOME Backend -- Purchase Processor (Sprint 6.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Core purchase distribution: investor pays, platform receives,
#   company gets its share. Platform keeps the remainder.
#
# DISTRIBUTION FLOW:
#   1. Investor active_ledger: -amount_cents
#   2. Platform passive_ledger: +amount_cents (full amount lands here)
#   3. Platform passive_ledger: -(company_pct * amount)
#   4. Company passive_ledger: +(company_pct * amount)
#   -- Platform remainder stays implicitly (already credited in step 2)
#
# AGENT COMMISSIONS:
#   Handled by ReferralProcessor (Sprint 7.2), not here.
#   Agent percentages from distribution_config are reserved but not
#   distributed until ReferralProcessor runs.
#
# ROUNDING:
#   All amounts computed via round(pct * amount_cents). Banker's rounding
#   ensures fair distribution. Any sub-cent remainder stays on Platform.
#
# INVARIANT:
#   SUM(entries.amount_cents) == 0 for the returned Transaction.
# =============================================================================

from app.core.constants import LedgerReason
from app.modules.processors.base import (
    LedgerEntry,
    PurchaseContext,
    Transaction,
)


class PurchaseProcessor:
    """Distribute purchase funds: investor -> platform -> company."""

    def process(self, context: PurchaseContext) -> list[Transaction]:
        """Generate sale transaction with distribution entries.

        Returns a single Transaction with legal_basis="sale".
        """
        amount = context.amount_cents
        dist = context.distribution_config
        company_pct = dist["company_pct"]
        company_share = round(company_pct * amount)

        # Placeholder purchase_id for reason strings.
        # Real UUID is assigned by execute_purchase() after processing.
        # Processors use "{purchase_id}" placeholder -- execute_purchase()
        # replaces it with the actual ID before writing to DB.
        pid = "{purchase_id}"

        entries: list[LedgerEntry] = []

        # 1. Debit investor's active_ledger.
        entries.append(LedgerEntry(
            user_id=context.investor_id,
            ledger_type="active",
            amount_cents=-amount,
            reason=LedgerReason.PURCHASE.format(purchase_id=pid),
            origin_payment_id=context.origin_payment_id,
            frozen_until=context.frozen_until,
        ))

        # 2. Credit platform's passive_ledger (full amount).
        entries.append(LedgerEntry(
            user_id=context.platform_user_id,
            ledger_type="passive",
            amount_cents=amount,
            reason=LedgerReason.PURCHASE.format(purchase_id=pid),
            origin_payment_id=context.origin_payment_id,
            frozen_until=context.frozen_until,
        ))

        # 3+4. Distribute company share: platform -> company.
        if company_share > 0:
            reason = LedgerReason.DISTRIBUTION_COMPANY.format(
                company_id=str(context.company_id),
                purchase_id=pid,
            )
            entries.append(LedgerEntry(
                user_id=context.platform_user_id,
                ledger_type="passive",
                amount_cents=-company_share,
                reason=reason,
                origin_payment_id=context.origin_payment_id,
                frozen_until=context.frozen_until,
            ))
            entries.append(LedgerEntry(
                user_id=context.company_user_id,
                ledger_type="passive",
                amount_cents=company_share,
                reason=reason,
                origin_payment_id=context.origin_payment_id,
                frozen_until=context.frozen_until,
            ))

        return [Transaction(
            reason=LedgerReason.PURCHASE.format(purchase_id=pid),
            legal_basis="sale",
            entries=entries,
            units=context.units,
        )]
