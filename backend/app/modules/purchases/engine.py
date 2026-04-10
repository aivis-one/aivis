# =============================================================================
# CBSHOME Backend -- Purchase Engine (Sprint 6.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Shared financial operation core. Accepts a fully-built PurchaseContext,
#   runs ProcessorRegistry, writes Purchase records + ledger entries.
#   Used by both instant purchases (purchases/service.py) and installment
#   tranche payments (installments/service.py).
#
# ENGINE CONTRACT:
#   1. Context is immutable on input -- engine never computes frozen_until,
#      distribution_config, or any other context field. Caller builds it.
#   2. If amount_cents > 0: advisory lock + balance check.
#      If amount_cents == 0: skip lock + balance (gift/bonus scenario).
#   3. Run ProcessorRegistry -> list[Transaction] (SUM=0 invariant).
#   4. Write Purchase records + ledger entries atomically.
#   5. Record audit events.
#
# COMMIT RULE (P-01):
#   Engine never commits. Caller (get_db_session) manages the transaction.
#
# AML NOTE:
#   Purchase saga does NOT call validate_route(). This is a controlled
#   system operation: investor active -> platform passive is always allowed.
#   See CBSHOME-Design-Document.md decision P5-01.
# =============================================================================

from datetime import datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError
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

logger = structlog.get_logger()


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
        BadRequestError: Insufficient balance.
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
            raise BadRequestError(
                f"Insufficient balance: {available} cents available, "
                f"{context.amount_cents} cents required"
            )

    # -- 2. Run processors --
    registry = ProcessorRegistry(
        investor_portfolio_cents=investor_portfolio_cents,
    )
    transactions = registry.run_all(context)

    # -- 3. Write to DB --
    purchases = await _write_transactions(
        session=session,
        transactions=transactions,
        context=context,
    )

    # -- 4. Audit --
    for purchase in purchases:
        await record_audit(
            session=session,
            event=(
                "purchase.created"
                if purchase.legal_basis == PurchaseLegalBasis.SALE
                else "purchase.gift_created"
            ),
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
# Internal helpers
# ---------------------------------------------------------------------------


async def _write_transactions(
    session: AsyncSession,
    transactions: list[Transaction],
    context: PurchaseContext,
) -> list[Purchase]:
    """Write Purchase records and ledger entries for all transactions.

    Each Transaction becomes one Purchase record. Ledger entries from
    the transaction are written via record_active/passive_ledger().

    The "{purchase_id}" placeholder in reason strings is replaced with
    the actual Purchase.id after creation.
    """
    purchases: list[Purchase] = []

    for txn in transactions:
        # Determine paid_cents: 0 for gifts, full amount for sale/tranche.
        if txn.legal_basis == PurchaseLegalBasis.GIFT:
            paid_cents = 0
        else:
            paid_cents = context.amount_cents

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
        )
        session.add(purchase)
        await session.flush()

        # Write ledger entries with real purchase_id in reason.
        purchase_id_str = str(purchase.id)

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

        purchases.append(purchase)

    return purchases
