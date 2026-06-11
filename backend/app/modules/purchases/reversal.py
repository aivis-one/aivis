# =============================================================================
# CBSHOME Backend -- Purchase Reversal Service (R-2.2 Block B)
# =============================================================================
#
# RESPONSIBILITY:
#   reverse_purchase() -- manual staff chargeback of a single Purchase:
#                         unwind its full money graph (investor debit,
#                         platform credit, company distribution, agent
#                         commissions), flip the Purchase to REVERSED.
#
# WHY A SEPARATE OPERATION FROM payments/reversal.py:
#   Payment reversal unwinds by origin_payment_id -- which only
#   FROZEN-funded purchases inherit (compute_frozen_context). A
#   purchase paid from CONFIRMED funds carries origin_payment_id=None
#   and is unreachable from any payment. This service captures the
#   purchase's money graph by REASON instead: every entry of the
#   purchase transaction embeds the purchase id
#   ("purchase:{id}" / "gift:{id}" primary entries,
#    "distribution:company:{cid}:{id}", "commission:l{n}:{agent}:{id}"
#    -- see purchases/engine.write_transactions and processors/*).
#
# CAPTURE PATTERN:
#   reason LIKE '%{purchase_id}%'
#   AND reason NOT LIKE '%:reversal'        (never re-capture mirrors)
#   AND status IN (frozen, confirmed)       (originals only)
#   across BOTH ledgers. A UUIDv4 substring cannot collide with
#   anything but this purchase's own entries.
#
# MONEY SEMANTICS:
#   The investor's debit flips to REVERSED -> their spendable balance
#   RISES by paid_cents (refund). Platform / company / agent credits
#   flip too (clawback). The original+mirror pairs keep all four R-2.1
#   invariants (see payments/reversal.py MIRROR ENTRIES): both rows
#   REVERSED, pair sums to zero, S-08 sees no confirmed rows, S-09
#   pairs 1:1.
#
# FROZEN-FUNDED PURCHASES:
#   The endpoint works for them as well -- reason capture does not
#   depend on origin_payment_id, and the funding Payment itself is NOT
#   touched (the deposit stays on the books; only the purchase money
#   returns to the investor's balance). A later reversal of that
#   payment unwinds only the deposit: this service already flipped the
#   purchase entries to REVERSED, so the payment-side status filter
#   skips them (pinned by test).
#
# OUT OF SCOPE:
#   Installment-tranche purchases -> BadRequestError. Their unwind
#   crosses plan/tranche state (IS-semaphores) and is a separate task.
#
# UNITS:
#   Return to the pool implicitly: pool consumption is SUM(units) over
#   ACTIVE purchases (pools/service.get_pool_consumed), so the status
#   flip alone frees them.
#
# CONCURRENCY:
#   SELECT FOR UPDATE on the Purchase row serializes parallel attempts;
#   the loser sees status=reversed and fails the ACTIVE guard.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.ledgers.service import record_active_ledger, record_passive_ledger
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction

logger = structlog.get_logger()

# Statuses eligible for reversal -- mirrors payments/reversal.py.
_REVERSIBLE_STATUSES = frozenset({LedgerStatus.FROZEN, LedgerStatus.CONFIRMED})


async def reverse_purchase(
    purchase_id: UUID,
    staff_id: UUID,
    session: AsyncSession,
    *,
    reason: str | None = None,
) -> dict:
    """Manually reverse a single purchase (staff chargeback).

    Captures the purchase's full money graph by reason across both
    ledgers, writes mirror entries, flips originals AND mirrors to
    REVERSED (R-2.1 invariants), flips the Purchase to REVERSED.
    Net effect: the investor is refunded paid_cents; platform /
    company / agents are clawed back; units leave pool consumption.

    Args:
        purchase_id: The purchase to reverse.
        staff_id: Staff member performing the reversal.
        session: Active DB session. Caller manages commit (P-01).
        reason: Optional human-readable reason for audit.

    Returns:
        Dict: purchase_id, total_reversed_cents, counts per ledger,
        units_returned, affected user ids.

    Raises:
        NotFoundError: Purchase not found.
        BadRequestError: Purchase not ACTIVE, or installment-tranche.
    """
    # 1. Load with row lock to serialize concurrent reversals.
    stmt = (
        select(Purchase)
        .where(Purchase.id == purchase_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    purchase = result.scalar_one_or_none()

    if purchase is None:
        raise NotFoundError("Purchase not found")

    # 2. Guards: tranche purchases are out of scope; only ACTIVE
    # purchases are reversible (repeat reversal -> 400).
    if purchase.legal_basis == PurchaseLegalBasis.INSTALLMENT_TRANCHE:
        raise BadRequestError(
            "Installment-tranche purchases cannot be reversed here -- "
            "their unwind crosses plan/tranche state (separate task)"
        )
    if purchase.status != PurchaseStatus.ACTIVE:
        raise BadRequestError(
            f"Purchase is not active (status={purchase.status!r})"
        )

    pid = str(purchase_id)

    # 3. Capture the money graph by reason (see CAPTURE PATTERN).
    active_stmt = select(ActiveLedger).where(
        ActiveLedger.reason.like(f"%{pid}%"),
        ~ActiveLedger.reason.like("%:reversal"),
        ActiveLedger.status.in_(_REVERSIBLE_STATUSES),
    )
    active_entries = list(
        (await session.execute(active_stmt)).scalars().all()
    )

    passive_stmt = select(PassiveLedger).where(
        PassiveLedger.reason.like(f"%{pid}%"),
        ~PassiveLedger.reason.like("%:reversal"),
        PassiveLedger.status.in_(_REVERSIBLE_STATUSES),
    )
    passive_entries = list(
        (await session.execute(passive_stmt)).scalars().all()
    )

    affected_user_ids: set[UUID] = set()
    total_reversed_cents = 0

    # 4. Mirror + flip BOTH rows to REVERSED -- identical mechanics to
    # payments/reversal.py (R-2.1: all four ledger invariants hold).
    for entry in active_entries:
        mirror = await record_active_ledger(
            session,
            user_id=entry.user_id,
            amount_cents=-entry.amount_cents,
            status=LedgerStatus.CONFIRMED,
            reason=f"{entry.reason}:reversal",
            origin_payment_id=entry.origin_payment_id,
        )
        mirror.status = LedgerStatus.REVERSED
        entry.status = LedgerStatus.REVERSED
        affected_user_ids.add(entry.user_id)
        total_reversed_cents += abs(entry.amount_cents)

    for entry in passive_entries:
        mirror = await record_passive_ledger(
            session,
            user_id=entry.user_id,
            amount_cents=-entry.amount_cents,
            status=LedgerStatus.CONFIRMED,
            reason=f"{entry.reason}:reversal",
            origin_payment_id=entry.origin_payment_id,
        )
        mirror.status = LedgerStatus.REVERSED
        entry.status = LedgerStatus.REVERSED
        affected_user_ids.add(entry.user_id)
        total_reversed_cents += abs(entry.amount_cents)

    # 5. Flip the Purchase. Units return to the pool implicitly
    # (consumption counts ACTIVE purchases only).
    purchase.status = PurchaseStatus.REVERSED
    await session.flush()

    # 6. Audit.
    await record_audit(
        session=session,
        event="purchase.chargeback",
        actor_id=staff_id,
        actor_type="staff",
        target_type="purchase",
        target_id=purchase_id,
        data={
            "trigger": "manual",
            "total_reversed_cents": total_reversed_cents,
            "active_entries_reversed": len(active_entries),
            "passive_entries_reversed": len(passive_entries),
            "units_returned": purchase.units,
            "investor_id": str(purchase.investor_id),
            "affected_user_ids": [str(uid) for uid in affected_user_ids],
            "reason": reason,
        },
    )

    # 7. Transaction log: purchase:reversed for the investor,
    # reversal:completed for the staff who performed it (same pairing
    # as the payment reversal, Sprint 6.4).
    await record_transaction(
        session,
        user_id=purchase.investor_id,
        type=TransactionType.PURCHASE_REVERSED,
        amount_cents=purchase.paid_cents,
        reference_id=purchase_id,
        reference_type=ReferenceType.PURCHASE,
        details={
            "trigger": "manual",
            "units": purchase.units,
            "reason": reason,
        },
    )
    await record_transaction(
        session,
        user_id=staff_id,
        type=TransactionType.REVERSAL_COMPLETED,
        amount_cents=total_reversed_cents,
        reference_id=purchase_id,
        reference_type=ReferenceType.PURCHASE,
        details={
            "reason": reason,
            "active_entries_reversed": len(active_entries),
            "passive_entries_reversed": len(passive_entries),
            "affected_user_ids": [str(uid) for uid in affected_user_ids],
        },
    )

    logger.info(
        "purchase_reversed",
        purchase_id=pid,
        staff_id=str(staff_id),
        total_reversed_cents=total_reversed_cents,
        active_entries=len(active_entries),
        passive_entries=len(passive_entries),
        units_returned=purchase.units,
        reason=reason,
    )

    return {
        "purchase_id": purchase_id,
        "total_reversed_cents": total_reversed_cents,
        "active_entries_reversed": len(active_entries),
        "passive_entries_reversed": len(passive_entries),
        "units_returned": purchase.units,
        "affected_user_ids": list(affected_user_ids),
    }
