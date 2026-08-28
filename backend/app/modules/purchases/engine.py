# =============================================================================
# AIVIS.ONE Backend -- Purchase Engine (Sprint 6.2, fix #35, updated Sprint 6.4,
#                                       Refactor 2 iter 2.4)
# =============================================================================
#
# RESPONSIBILITY:
#   Shared financial operation core. Accepts a fully-built PurchaseContext,
#   runs ProcessorRegistry, writes Purchase records + ledger entries.
#   Used by both instant purchases (purchases/service.py) and installment
#   tranche payments (installments/service.py).
#
# PUBLIC API:
#   execute()            -- full flow: lock + balance + registry + write + audit
#   write_transactions() -- lower-level: write Transaction objects to DB
#                           Used by complete_plan() for fixed completion bonuses
#                           that don't go through ProcessorRegistry.
#
# ENGINE CONTRACT:
#   1. Context is immutable on input -- engine never computes frozen_until,
#      distribution_config, or any other context field. Caller builds it.
#   2. If amount_cents > 0: advisory lock + balance check.
#      If amount_cents == 0: skip lock + balance (gift/bonus scenario).
#   3. Run ProcessorRegistry -> list[Transaction] (SUM=0 invariant).
#   4. Write Purchase records + ledger entries atomically.
#   5. Record audit events.
#   6. Write transaction log entries (Sprint 6.4).
#
# TRANSACTION LOG (Sprint 6.4):
#   write_transactions() records purchase:completed for SALE,
#   purchase:gift for GIFT. INSTALLMENT_TRANCHE is handled by
#   installments/service.py (has plan context for reference_id).
#
# Refactor 2 iter 2.4 (R2 §5.1) -- TEMPLATE SNAPSHOT:
#   For every Purchase row created in write_transactions(), the engine
#   resolves the active document template for (company_id, kind,
#   language) via find_active_template(). The found template's id is
#   snapshotted onto Purchase.purchase_agreement_template_id.
#
#   The kind is derived from legal_basis via BASIS_TO_KIND:
#     sale                 -> purchase_agreement
#     gift                 -> gift_certificate
#     installment_tranche  -> installment_subcontract
#
#   ownership_certificate is intentionally NOT in this map -- it has
#   no per-Purchase snapshot (see R2 §5.3); the renderer resolves it
#   fresh on every call.
#
#   On NULL fallthrough (all 4 fallback stages miss, platform default
#   genuinely absent) we:
#     - persist the Purchase with template_id = NULL (financial
#       transaction > document rendering),
#     - emit a structured log: `template_missing`,
#     - record an audit event: `purchase.template_missing` so Staff
#       sees the broken Purchase in the audit dashboard and can fix it
#       with `aivis storage reconcile-platform-templates`.
#
# COMMIT RULE (P-01):
#   Engine never commits. Caller (get_db_session) manages the transaction.
#
# AML NOTE:
#   Purchase saga does NOT call validate_route(). This is a controlled
#   system operation: investor active -> platform passive is always allowed.
#   See AIVIS-Design-Document.md decision P5-01.
# =============================================================================

from datetime import datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms import comms_configured
from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event
from app.core.exceptions import InsufficientBalanceError
from app.modules.commissions.service import COMMISSION_REASON_RE
from app.modules.companies.constants import DocumentTemplateKind
from app.modules.companies.service import find_active_template
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import (
    get_active_balance,
    record_active_ledger,
    record_passive_ledger,
)
from app.modules.processors.base import PurchaseContext, Transaction
from app.modules.processors.registry import ProcessorRegistry
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction

logger = structlog.get_logger()

# Mapping from legal_basis to transaction log type.
# INSTALLMENT_TRANCHE is not here -- handled by installments/service.py.
_LEGAL_BASIS_TO_TXN_TYPE: dict[str, str] = {
    PurchaseLegalBasis.SALE: TransactionType.PURCHASE_COMPLETED,
    PurchaseLegalBasis.GIFT: TransactionType.PURCHASE_GIFT,
}

# Refactor 2 iter 2.4: Purchase legal_basis -> document template kind
# (R2 §5.1). ownership_certificate is intentionally absent -- it has
# no per-Purchase snapshot.
_BASIS_TO_TEMPLATE_KIND: dict[str, str] = {
    PurchaseLegalBasis.SALE: DocumentTemplateKind.PURCHASE_AGREEMENT,
    PurchaseLegalBasis.GIFT: DocumentTemplateKind.GIFT_CERTIFICATE,
    PurchaseLegalBasis.INSTALLMENT_TRANCHE: DocumentTemplateKind.INSTALLMENT_SUBCONTRACT,
}


async def execute(
    context: PurchaseContext,
    session: AsyncSession,
    *,
    investor_portfolio_cents: int = 0,
) -> list[Purchase]:
    """Execute a financial purchase operation from a fully-built context.

    This is the shared core used by both instant purchases and
    installment tranche payments. The caller is responsible for:
      - Building the PurchaseContext with all fields populated
      - Computing frozen_until and origin_payment_id
      - Resolving distribution_config and bonuses

    Engine handles:
      - Advisory lock (if amount_cents > 0)
      - Balance check (if amount_cents > 0)
      - ProcessorRegistry execution
      - Purchase + ledger entry writes
      - Audit events

    Args:
        context: Fully-built PurchaseContext. Immutable -- engine never
            modifies it.
        session: Active DB session. Caller manages commit (P-01).
        investor_portfolio_cents: SUM(paid_cents) for GiftProcessor
            portfolio_size_gte condition. Default 0.

    Returns:
        List of Purchase records created (sale + optional gifts).

    Raises:
        InsufficientBalanceError: Balance too low for amount_cents.
    """
    # -- 1. Advisory lock + balance check (only when money moves) --
    if context.amount_cents > 0:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": context.investor_id.int & 0x7FFFFFFFFFFFFFFF},
        )

        balance = await get_active_balance(session, context.investor_id)
        available = balance["frozen"] + balance["confirmed"]

        if available < context.amount_cents:
            raise InsufficientBalanceError(
                available=available,
                required=context.amount_cents,
            )

    # -- 2. Run processors --
    registry = ProcessorRegistry(
        investor_portfolio_cents=investor_portfolio_cents,
    )
    transactions = registry.run_all(context)

    # -- 3. Write to DB --
    purchases = await write_transactions(
        session=session,
        transactions=transactions,
        context=context,
    )

    # -- 4. Audit --
    for purchase in purchases:
        if purchase.legal_basis == PurchaseLegalBasis.SALE:
            event = "purchase.created"
        elif purchase.legal_basis == PurchaseLegalBasis.INSTALLMENT_TRANCHE:
            event = "purchase.tranche_created"
        else:
            event = "purchase.gift_created"
        await record_audit(
            session=session,
            event=event,
            actor_id=context.investor_id,
            actor_type="user",
            target_type="purchase",
            target_id=purchase.id,
            data={
                "product_id": str(context.product_id),
                "company_id": str(context.company_id),
                "legal_basis": purchase.legal_basis,
                "units": purchase.units,
                "paid_cents": purchase.paid_cents,
            },
        )

    logger.info(
        "engine_execute_completed",
        investor_id=str(context.investor_id),
        product_id=str(context.product_id),
        amount_cents=context.amount_cents,
        purchase_count=len(purchases),
    )

    return purchases


# ---------------------------------------------------------------------------
# Transaction writer (public -- used by complete_plan for fixed bonuses)
# ---------------------------------------------------------------------------


async def _snapshot_template_id(
    session: AsyncSession,
    *,
    company_id: UUID,
    legal_basis: str,
    language: str,
    actor_id: UUID,
) -> UUID | None:
    """Resolve the active template for (company, kind, language) and return
    its id. On any miss, log + audit + return None.

    R2 §5.1: NULL fallthrough is allowed and is treated as a broken-infra
    signal (structlog + audit event `purchase.template_missing`). The
    Purchase row is still created so the financial transaction survives;
    rendering will surface 500 at the agreement endpoint.

    Args:
        session: Active DB session (engine never commits).
        company_id: Owning company.
        legal_basis: One of PurchaseLegalBasis values.
        language: ISO 639-1 from PurchaseContext.investor_language.
        actor_id: investor_id from the context (audit attribution).

    Returns:
        Template UUID or None.
    """
    kind = _BASIS_TO_TEMPLATE_KIND.get(legal_basis)
    if kind is None:
        # No template kind associated with this legal_basis. Should not
        # occur with current values, but keeping the helper defensive
        # so a future PurchaseLegalBasis value doesn't silently snapshot
        # against the wrong kind.
        logger.warning(
            "template_kind_unknown_for_legal_basis",
            legal_basis=legal_basis,
            company_id=str(company_id),
        )
        return None

    template = await find_active_template(
        company_id=company_id,
        kind=kind,
        language=language,
        session=session,
    )

    if template is not None:
        return template.id

    # NULL fallthrough -- platform default genuinely missing.
    logger.error(
        "template_missing",
        company_id=str(company_id),
        kind=kind,
        language=language,
    )
    await record_audit(
        session=session,
        event="purchase.template_missing",
        actor_id=actor_id,
        actor_type="system",
        target_type="company",
        target_id=company_id,
        data={
            "kind": kind,
            "language": language,
        },
    )
    return None


async def write_transactions(
    session: AsyncSession,
    transactions: list[Transaction],
    context: PurchaseContext,
) -> list[Purchase]:
    """Write Purchase records and ledger entries for all transactions.

    Each Transaction becomes one Purchase record. Ledger entries from
    the transaction are written via record_active/passive_ledger().

    The "{purchase_id}" placeholder in reason strings is replaced with
    the actual Purchase.id after creation.

    Sprint 6.4: writes transaction log entries for SALE and GIFT.
    INSTALLMENT_TRANCHE is handled by installments/service.py.

    Refactor 2 iter 2.4: every Purchase row receives
    purchase_agreement_template_id snapshotted from find_active_template
    (R2 §5.1). NULL fallthrough writes structlog + audit `template_missing`
    and persists the Purchase regardless.

    Public API: used by engine.execute() and directly by
    installments/service.py complete_plan() for completion bonuses.
    Caller must ensure SUM=0 invariant on each Transaction.
    """
    purchases: list[Purchase] = []

    for txn in transactions:
        # Determine paid_cents: 0 for gifts, full amount for sale/tranche.
        if txn.legal_basis == PurchaseLegalBasis.GIFT:
            paid_cents = 0
        else:
            paid_cents = context.amount_cents

        # Refactor 2 iter 2.4: resolve template snapshot per-Purchase.
        # Each Transaction in a multi-Transaction batch (sale + bonus
        # gifts from purchase_config) has its own legal_basis, so the
        # kind / template can legitimately differ across the batch.
        template_id = await _snapshot_template_id(
            session,
            company_id=context.company_id,
            legal_basis=txn.legal_basis,
            language=context.investor_language,
            actor_id=context.investor_id,
        )

        # Create Purchase record.
        purchase = Purchase(
            investor_id=context.investor_id,
            product_id=context.product_id,
            company_id=context.company_id,
            legal_basis=txn.legal_basis,
            units=txn.units,
            paid_cents=paid_cents,
            price_per_unit_cents=context.price_per_unit_cents,
            status=PurchaseStatus.ACTIVE,
            purchase_agreement_template_id=template_id,
        )
        session.add(purchase)
        await session.flush()

        # Write ledger entries with real purchase_id in reason.
        purchase_id_str = str(purchase.id)
        notify_commissions = comms_configured()

        for entry in txn.entries:
            reason = entry.reason.replace("{purchase_id}", purchase_id_str)

            # Determine ledger status from frozen_until.
            ledger_status = (
                LedgerStatus.FROZEN
                if entry.frozen_until is not None
                else LedgerStatus.CONFIRMED
            )

            if entry.ledger_type == "active":
                await record_active_ledger(
                    session,
                    user_id=entry.user_id,
                    amount_cents=entry.amount_cents,
                    status=ledger_status,
                    reason=reason,
                    frozen_until=entry.frozen_until,
                    origin_payment_id=entry.origin_payment_id,
                )
            else:
                await record_passive_ledger(
                    session,
                    user_id=entry.user_id,
                    amount_cents=entry.amount_cents,
                    status=ledger_status,
                    reason=reason,
                    frozen_until=entry.frozen_until,
                    origin_payment_id=entry.origin_payment_id,
                )

                # Batch 6 (2026-08-28): commission.purchase_credited --
                # the per-purchase L1/L2/L3 referral split (referral.py),
                # DISTINCT from commission.credited (the periodic volume
                # bonus payout worker, a different code path entirely).
                # ReferralProcessor writes TWO passive entries per level
                # sharing one reason -- a Platform debit and an Agent
                # credit -- and only the credit side should be notified
                # (the debit is Platform's own internal ledger, not a
                # user-facing event). COMMISSION_REASON_RE (reused from
                # commissions/service.py, not reinvented) matches the
                # post-replace reason "commission:l{level}:{agent_id}:
                # {purchase_id}"; entry.amount_cents > 0 selects the
                # credit side (the debit is negative by construction in
                # referral.py). entry.user_id IS the agent_id here --
                # ReferralProcessor sets it directly when building the
                # credit LedgerEntry, so there is no need to re-parse it
                # out of the reason string, only to confirm the format.
                if notify_commissions and entry.amount_cents > 0:
                    match = COMMISSION_REASON_RE.match(reason)
                    if match is not None:
                        level = match.group(1)
                        amount = f"{entry.amount_cents / 100:,.2f}"
                        await emit_event(
                            session,
                            EVENT_NOTIFICATION_REQUEST,
                            {
                                # One credit entry per (level, purchase),
                                # ever -- reason embeds the real
                                # purchase_id post-replace and a
                                # Transaction is written exactly once per
                                # purchase, so the reason string alone is
                                # a safe, permanent dedup key.
                                "idempotency_key": f"commission-purchase:{reason}",
                                "type": "commission.purchase_credited",
                                "target_type": "user",
                                "target_value": str(entry.user_id),
                                "title": "Commission earned",
                                "body": (
                                    f"You earned a ${amount} level-{level} "
                                    f"commission on a purchase."
                                ),
                            },
                        )

        # Sprint 6.4: Transaction log entry.
        # INSTALLMENT_TRANCHE is recorded by installments/service.py
        # which has the plan_id for reference.
        txn_type = _LEGAL_BASIS_TO_TXN_TYPE.get(txn.legal_basis)
        if txn_type is not None:
            await record_transaction(
                session,
                user_id=context.investor_id,
                type=txn_type,
                amount_cents=-paid_cents if paid_cents > 0 else 0,
                reference_id=purchase.id,
                reference_type=ReferenceType.PURCHASE,
                details={
                    "product_id": str(context.product_id),
                    "company_id": str(context.company_id),
                    "units": txn.units,
                    "price_per_unit_cents": context.price_per_unit_cents,
                    "legal_basis": txn.legal_basis,
                },
            )

        purchases.append(purchase)

    return purchases
