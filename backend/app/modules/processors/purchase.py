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
        """Generate sale/tranche transaction with distribution entries.

        Returns a single Transaction whose legal_basis comes from
        context.legal_basis (default "sale") -- installments call this
        via engine.execute with legal_basis="installment_tranche" so
        the resulting Purchase row is correctly tagged in the UI and
        the primary ledger entries carry the canonical
        "installment:tranche:{id}" reason (not "purchase:{id}").
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

        # Primary ledger reason for the investor -> platform entries.
        # Installment tranches hand a fully-resolved reason in via
        # context.reason (tranche_id is known at pay_tranche time);
        # sale path keeps the {purchase_id} placeholder for the engine.
        primary_reason = (
            context.reason
            if context.reason is not None
            else LedgerReason.PURCHASE.format(purchase_id=pid)
        )

        entries: list[LedgerEntry] = []

        # 1. Debit investor's active_ledger.
        entries.append(LedgerEntry(
            user_id=context.investor_id,
            ledger_type="active",
            amount_cents=-amount,
            reason=primary_reason,
            origin_payment_id=context.origin_payment_id,
            frozen_until=context.frozen_until,
        ))

        # 2. Credit platform's passive_ledger (full amount).
        entries.append(LedgerEntry(
            user_id=context.platform_user_id,
            ledger_type="passive",
            amount_cents=amount,
            reason=primary_reason,
            origin_payment_id=context.origin_payment_id,
            frozen_until=context.frozen_until,
        ))

        # 3+4. Distribute company share: platform -> company.
        # Distribution keeps its own canonical reason regardless of the
        # triggering operation -- semaphores group by "distribution:".
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
            reason=primary_reason,
            legal_basis=context.legal_basis,
            entries=entries,
            units=context.units,
        )]
