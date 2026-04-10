# =============================================================================
# CBSHOME Backend -- Payment Reversal Service (Sprint 5.3, fix review)
# =============================================================================
#
# RESPONSIBILITIES:
#   reverse_payment() -- chargeback: mark Payment as reversed, create mirror
#                        ledger entries, mark originals as reversed.
#
# REVERSAL FLOW (from CBSHOME-Financial-System.md section 5.5):
#   1. SELECT FOR UPDATE Payment (serialize concurrent reversals)
#   2. Validate status transition -> reversed
#   3. SELECT active_ledger WHERE origin_payment_id=X AND status IN (frozen, confirmed)
#   4. SELECT passive_ledger WHERE origin_payment_id=X AND status IN (frozen, confirmed)
#   5. For each entry:
#        INSERT mirror entry: amount=-original, reason=original+":reversal",
#                             status=confirmed (reversal acts immediately)
#        UPDATE original -> status=reversed
#   6. Payment -> status=reversed
#   7. Audit: payment.chargeback
#
# MIRROR ENTRIES:
#   Created via record_active/passive_ledger() with status=confirmed.
#   This ensures full audit trail and correct balance calculation.
#   Balance may go negative -- this is intentional (user owes platform).
#
# ORIGINAL ENTRIES:
#   Status updated directly via ORM (bypassing _WRITABLE_STATUSES guard).
#   This is the only authorized path to set status=reversed.
#
# TOTAL_REVERSED_CENTS:
#   Calculated from the sum of actual reversed entries, not payment.amount_cents.
#   These may diverge when a payment has multiple ledger entries (Phase 6+ saga).
#
# CONCURRENT REVERSAL PROTECTION:
#   SELECT FOR UPDATE on Payment row serializes parallel chargeback attempts.
#   Second request waits for first to commit, then sees status=reversed and fails.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import NotFoundError
from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.ledgers.service import record_active_ledger, record_passive_ledger
from app.modules.payments.constants import PaymentStatus, validate_payment_status_transition
from app.modules.payments.models import Payment

logger = structlog.get_logger()

# Statuses eligible for reversal -- frozen and confirmed entries only.
_REVERSIBLE_STATUSES = frozenset({LedgerStatus.FROZEN, LedgerStatus.CONFIRMED})


async def reverse_payment(
    payment_id: UUID,
    staff_id: UUID,
    session: AsyncSession,
    *,
    reason: str | None = None,
) -> dict:
    """Reverse a payment (chargeback).

    Creates mirror ledger entries with negative amounts and marks
    originals as reversed. Payment status transitions to reversed.

    Uses SELECT FOR UPDATE to prevent concurrent reversals of the
    same payment creating duplicate mirror entries.

    Args:
        payment_id: The payment to reverse.
        staff_id: Staff member performing the reversal.
        session: Active DB session. Caller manages commit (P-01).
        reason: Optional human-readable reason for audit.

    Returns:
        Dict with reversal summary: payment_id, total_reversed_cents,
        counts of reversed entries, affected user IDs.

    Raises:
        NotFoundError: If payment not found.
        BadRequestError: If payment status transition is invalid
            (e.g., already reversed or failed).
    """
    # 1. Load with row lock to serialize concurrent reversals.
    stmt = select(Payment).where(Payment.id == payment_id).with_for_update()
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()

    if payment is None:
        raise NotFoundError("Payment not found")

    # 2. Validate status transition.
    validate_payment_status_transition(payment.status, PaymentStatus.REVERSED)

    # 3. Find active_ledger entries linked to this payment.
    active_stmt = select(ActiveLedger).where(
        ActiveLedger.origin_payment_id == payment_id,
        ActiveLedger.status.in_(_REVERSIBLE_STATUSES),
    )
    active_result = await session.execute(active_stmt)
    active_entries = list(active_result.scalars().all())

    # 4. Find passive_ledger entries linked to this payment.
    passive_stmt = select(PassiveLedger).where(
        PassiveLedger.origin_payment_id == payment_id,
        PassiveLedger.status.in_(_REVERSIBLE_STATUSES),
    )
    passive_result = await session.execute(passive_stmt)
    passive_entries = list(passive_result.scalars().all())

    affected_user_ids: set[UUID] = set()
    total_reversed_cents = 0

    # 5. Create mirror entries for active_ledger and mark originals reversed.
    for entry in active_entries:
        await record_active_ledger(
            session,
            user_id=entry.user_id,
            amount_cents=-entry.amount_cents,
            status=LedgerStatus.CONFIRMED,
            reason=f"{entry.reason}:reversal",
            origin_payment_id=payment_id,
        )
        # Direct ORM update -- only authorized path to set reversed.
        entry.status = LedgerStatus.REVERSED
        affected_user_ids.add(entry.user_id)
        total_reversed_cents += abs(entry.amount_cents)

    # 6. Create mirror entries for passive_ledger and mark originals reversed.
    for entry in passive_entries:
        await record_passive_ledger(
            session,
            user_id=entry.user_id,
            amount_cents=-entry.amount_cents,
            status=LedgerStatus.CONFIRMED,
            reason=f"{entry.reason}:reversal",
            origin_payment_id=payment_id,
        )
        entry.status = LedgerStatus.REVERSED
        affected_user_ids.add(entry.user_id)
        total_reversed_cents += abs(entry.amount_cents)

    # 7. Update payment status.
    payment.status = PaymentStatus.REVERSED
    await session.flush()

    # 8. Audit.
    await record_audit(
        session=session,
        event="payment.chargeback",
        actor_id=staff_id,
        actor_type="staff",
        target_type="payment",
        target_id=payment_id,
        data={
            "total_reversed_cents": total_reversed_cents,
            "active_entries_reversed": len(active_entries),
            "passive_entries_reversed": len(passive_entries),
            "affected_user_ids": [str(uid) for uid in affected_user_ids],
            "reason": reason,
        },
    )

    logger.info(
        "payment_reversed",
        payment_id=str(payment_id),
        staff_id=str(staff_id),
        total_reversed_cents=total_reversed_cents,
        active_entries=len(active_entries),
        passive_entries=len(passive_entries),
        reason=reason,
    )

    return {
        "payment_id": payment_id,
        "total_reversed_cents": total_reversed_cents,
        "active_entries_reversed": len(active_entries),
        "passive_entries_reversed": len(passive_entries),
        "affected_user_ids": list(affected_user_ids),
    }
