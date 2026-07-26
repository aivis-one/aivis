# =============================================================================
# AIVIS.ONE Backend -- Payment Reversal Service (Sprint 5.3, fix review,
#                                              updated Sprint 6.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   reverse_payment() -- chargeback: mark Payment as reversed, create mirror
#                        ledger entries, mark originals as reversed.
#                        + write transaction log entries (Sprint 6.4)
#                        + flip frozen-funded purchases to REVERSED so the
#                          asset side unwinds with the money (R-2.2 Block A;
#                          units return to the pool implicitly -- pool
#                          consumption counts ACTIVE purchases only)
#
# REVERSAL FLOW (R47 invariant fix; supersedes the literal reading of
# AIVIS-Financial-System.md section 5.5 / P5-19 -- see MIRROR ENTRIES):
#   1. SELECT FOR UPDATE Payment (serialize concurrent reversals)
#   2. Validate status transition -> reversed
#   3. SELECT active_ledger WHERE origin_payment_id=X AND status IN (frozen, confirmed)
#   4. SELECT passive_ledger WHERE origin_payment_id=X AND status IN (frozen, confirmed)
#   5. For each entry:
#        INSERT mirror entry: amount=-original, reason=original+":reversal",
#                             then immediately flip mirror -> status=reversed
#        UPDATE original -> status=reversed
#   5b. Parse "purchase:{id}" / "gift:{id}" from captured active originals,
#       flip those Purchases -> REVERSED, log purchase:reversed (R-2.2)
#   6. Payment -> status=reversed
#   7. Audit: payment.chargeback
#   8. Transaction log: deposit:reversed + reversal:completed (Sprint 6.4)
#
# MIRROR ENTRIES (R47 -- the double-debit fix):
#   Mirrors are written through record_active/passive_ledger() (audit
#   trail, immutability doctrine intact) and then flipped to REVERSED
#   via the same authorized direct-ORM path as the originals.
#
#   WHY REVERSED AND NOT CONFIRMED. The system carries four invariants
#   that must hold simultaneously after a reversal:
#     * get_*_balance() EXCLUDES reversed entries;
#     * S-01: SUM(all entries INCLUDING reversed) = 0 -- the mirror
#       must exist to cancel the original in the global sum;
#     * S-08: NO CONFIRMED entries may reference a reversed Payment;
#     * S-09: every ":reversal" entry pairs with a reversed original.
#   A CONFIRMED mirror (the pre-R47 behaviour) broke two of them: the
#   user's balance dropped by 2x the deposit (original excluded AND
#   mirror subtracted -- an unspent reversed deposit left the user at
#   -X instead of 0), and S-08 flagged every reversal. A REVERSED
#   mirror satisfies all four: both rows are excluded from spendable
#   balance (net effect exactly -X: the deposit disappears), the pair
#   sums to zero inside S-01, S-08 sees no confirmed rows, S-09 pairs
#   1:1.
#
# SPENT-DEPOSIT SEMANTICS (corrected per R47 review; asset side R-2.2):
#   FROZEN-funded purchase debits INHERIT the deposit's
#   origin_payment_id (purchases/service.py compute_frozen_context),
#   so step 3 of this flow captures them too: the deposit credit AND
#   those purchase debits unwind together. Balance lands at exactly 0
#   and NO debt is recorded -- and the purchased ASSET is revoked in
#   the same operation: step 5b below flips those Purchases to
#   REVERSED (units leave pool consumption implicitly; pinned by
#   test_reverse_spent_frozen_deposit_unwinds_purchase_debit).
#   CONFIRMED-funded purchases carry origin_payment_id=None and stay
#   booked -- only there the balance goes genuinely negative
#   ("user owes platform"); their chargeback path is the manual
#   staff endpoint (purchases/reversal.py).
#
# ORIGINAL ENTRIES:
#   Status updated directly via ORM (bypassing _WRITABLE_STATUSES guard).
#   reverse_payment() is the only authorized path to set status=reversed
#   (applies to mirrors as well, see above).
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
from app.modules.installments.constants import (
    InstallmentTrancheStatus,
)
from app.modules.installments.models import (
    InstallmentPlan,
    InstallmentTranche,
)
from app.modules.installments.service import (
    unwind_plan_for_reversed_tranche,
)
from app.modules.purchases.constants import PurchaseStatus
from app.modules.purchases.models import Purchase
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction

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

    Creates mirror ledger entries with negative amounts; both the
    originals AND the mirrors end up status=reversed (R47 -- see the
    MIRROR ENTRIES header for the four invariants this satisfies).
    Net spendable-balance effect: exactly minus the reversed amounts.
    Payment status transitions to reversed.

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
    # R49-3.2: FOR UPDATE on the captured originals. The two reversal
    # paths (payment / purchase) hold different primary locks, so two
    # staff reversing a linked pair concurrently could both capture the
    # same rows and write duplicate mirrors. Locking the originals
    # serializes the capture: the loser re-reads after the winner's
    # commit, sees status=reversed and captures nothing.
    active_stmt = select(ActiveLedger).where(
        ActiveLedger.origin_payment_id == payment_id,
        ActiveLedger.status.in_(_REVERSIBLE_STATUSES),
    ).with_for_update()
    active_result = await session.execute(active_stmt)
    active_entries = list(active_result.scalars().all())

    # 4. Find passive_ledger entries linked to this payment.
    passive_stmt = select(PassiveLedger).where(
        PassiveLedger.origin_payment_id == payment_id,
        PassiveLedger.status.in_(_REVERSIBLE_STATUSES),
    ).with_for_update()
    passive_result = await session.execute(passive_stmt)
    passive_entries = list(passive_result.scalars().all())

    affected_user_ids: set[UUID] = set()
    total_reversed_cents = 0

    # 5. Create mirror entries for active_ledger and mark BOTH the
    # original and the mirror reversed (see MIRROR ENTRIES header).
    for entry in active_entries:
        mirror = await record_active_ledger(
            session,
            user_id=entry.user_id,
            amount_cents=-entry.amount_cents,
            status=LedgerStatus.CONFIRMED,
            reason=f"{entry.reason}:reversal",
            origin_payment_id=payment_id,
        )
        # Direct ORM updates -- reverse_payment() is the only
        # authorized path to set reversed (R47: the mirror too, so the
        # pair nets to zero in S-01 while BOTH stay out of spendable
        # balance and S-08 sees no confirmed rows).
        mirror.status = LedgerStatus.REVERSED
        entry.status = LedgerStatus.REVERSED
        affected_user_ids.add(entry.user_id)
        total_reversed_cents += abs(entry.amount_cents)

    # 6. Same for passive_ledger: mirror + flip both to reversed.
    for entry in passive_entries:
        mirror = await record_passive_ledger(
            session,
            user_id=entry.user_id,
            amount_cents=-entry.amount_cents,
            status=LedgerStatus.CONFIRMED,
            reason=f"{entry.reason}:reversal",
            origin_payment_id=payment_id,
        )
        mirror.status = LedgerStatus.REVERSED
        entry.status = LedgerStatus.REVERSED
        affected_user_ids.add(entry.user_id)
        total_reversed_cents += abs(entry.amount_cents)

    # 6b. R-2.2 Block A: flip the frozen-funded purchases whose money
    # was just unwound. One ACTIVE purchase == one investor debit with
    # reason "purchase:{id}" (or "gift:{id}" for bonus allocations, see
    # purchases/engine.write_transactions), so the captured active
    # originals are the authoritative purchase list. Distribution /
    # commission reasons live passive-side and are intentionally not
    # parsed (they would only duplicate ids). Installment-tranche
    # debits ("installment:tranche:{tranche_id}") cannot be resolved
    # to a Purchase from the reason -- their money unwinds with the
    # rest, the plan/purchase rows are the installment layer's problem
    # (out of R-2.2 scope; warn-logged so it is visible).
    purchase_ids: list[UUID] = []
    tranche_ids: list[UUID] = []
    for entry in active_entries:
        prefix, _, suffix = entry.reason.partition(":")
        if prefix == "installment":
            # Tranche-unwind (boss-locked, closes the R-2.2 accepted
            # risk): "installment:tranche:{tranche_id}" -- resolve the
            # tranche so step 6c can flip its Purchase, reverse the
            # tranche and default the plan.
            kind, _, tranche_suffix = suffix.partition(":")
            if kind == "tranche":
                try:
                    tranche_ids.append(UUID(tranche_suffix))
                except ValueError:
                    logger.warning(
                        "reversal_tranche_reason_unparseable",
                        payment_id=str(payment_id),
                        reason=entry.reason,
                    )
            continue
        if prefix not in ("purchase", "gift"):
            continue
        try:
            purchase_ids.append(UUID(suffix))
        except ValueError:
            continue

    purchases_reversed = 0
    purchase_ids_reversed: list[str] = []
    if purchase_ids:
        p_stmt = (
            select(Purchase)
            .where(Purchase.id.in_(purchase_ids))
            .with_for_update()
        )
        p_result = await session.execute(p_stmt)
        for purchase in p_result.scalars().all():
            if purchase.status == PurchaseStatus.REVERSED:
                # Defensive: a reversed purchase has no capturable
                # debit, so this should be unreachable.
                continue
            purchase.status = PurchaseStatus.REVERSED
            purchases_reversed += 1
            purchase_ids_reversed.append(str(purchase.id))
            # Units return to the pool implicitly: pool consumption is
            # SUM(units) over ACTIVE purchases (pools/service.py
            # get_pool_consumed), so the flip alone frees them.
            await record_transaction(
                session,
                user_id=purchase.investor_id,
                type=TransactionType.PURCHASE_REVERSED,
                amount_cents=purchase.paid_cents,
                reference_id=purchase.id,
                reference_type=ReferenceType.PURCHASE,
                details={
                    "trigger": "payment_reversal",
                    "payment_id": str(payment_id),
                    "units": purchase.units,
                    "reason": reason,
                },
            )

    # 6c. Tranche-unwind (boss-locked semantics; closes the R-2.2
    # "money unwound, purchase left" accepted risk). For every
    # installment-tranche debit this payment funded:
    #   * flip the tranche's Purchase to REVERSED (units leave the
    #     portfolio and pool consumption implicitly, same as 6b);
    #   * tranche -> terminal REVERSED, ACTIVE plan -> DEFAULTED via
    #     the installments unwind helper (remaining schedule
    #     cancelled, R51 pool reservation frees by status);
    #   * COMPLETED plans are flagged (audit + IS-05), never unwound.
    # FOR UPDATE on tranches and plans serializes with the
    # installment daemon (TD-042 pattern).
    tranches_unwound: list[dict] = []
    if tranche_ids:
        t_stmt = (
            select(InstallmentTranche)
            .where(InstallmentTranche.id.in_(tranche_ids))
            .with_for_update()
        )
        tranches = list((await session.execute(t_stmt)).scalars().all())

        plan_ids = {t.plan_id for t in tranches}
        pl_stmt = (
            select(InstallmentPlan)
            .where(InstallmentPlan.id.in_(plan_ids))
            .with_for_update()
        )
        plans = {
            pl.id: pl
            for pl in (await session.execute(pl_stmt)).scalars().all()
        }

        for tranche in tranches:
            if tranche.status == InstallmentTrancheStatus.REVERSED:
                # Defensive: a reversed tranche has no capturable debit.
                continue

            # Flip the tranche's Purchase -- same mechanics as 6b.
            if tranche.purchase_id is not None:
                t_purchase = await session.get(
                    Purchase, tranche.purchase_id, with_for_update=True
                )
                if (
                    t_purchase is not None
                    and t_purchase.status != PurchaseStatus.REVERSED
                ):
                    t_purchase.status = PurchaseStatus.REVERSED
                    purchases_reversed += 1
                    purchase_ids_reversed.append(str(t_purchase.id))
                    await record_transaction(
                        session,
                        user_id=t_purchase.investor_id,
                        type=TransactionType.PURCHASE_REVERSED,
                        amount_cents=t_purchase.paid_cents,
                        reference_id=t_purchase.id,
                        reference_type=ReferenceType.PURCHASE,
                        details={
                            "trigger": "payment_reversal",
                            "payment_id": str(payment_id),
                            "tranche_id": str(tranche.id),
                            "units": t_purchase.units,
                            "reason": reason,
                        },
                    )

            summary = await unwind_plan_for_reversed_tranche(
                plans[tranche.plan_id], tranche, session
            )
            tranches_unwound.append(summary)

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
            "purchases_reversed": purchases_reversed,
            "purchase_ids_reversed": purchase_ids_reversed,
            "affected_user_ids": [str(uid) for uid in affected_user_ids],
            "reason": reason,
        },
    )

    # 9. Transaction log (Sprint 6.4).
    # deposit:reversed for the payment owner.
    await record_transaction(
        session,
        user_id=payment.user_id,
        type=TransactionType.DEPOSIT_REVERSED,
        amount_cents=payment.amount_cents,
        reference_id=payment_id,
        reference_type=ReferenceType.PAYMENT,
        details={
            "reason": reason,
            "total_reversed_cents": total_reversed_cents,
        },
    )

    # reversal:completed for the staff who performed it.
    await record_transaction(
        session,
        user_id=staff_id,
        type=TransactionType.REVERSAL_COMPLETED,
        amount_cents=total_reversed_cents,
        reference_id=payment_id,
        reference_type=ReferenceType.PAYMENT,
        details={
            "reason": reason,
            "active_entries_reversed": len(active_entries),
            "passive_entries_reversed": len(passive_entries),
            "affected_user_ids": [str(uid) for uid in affected_user_ids],
        },
    )

    logger.info(
        "payment_reversed",
        payment_id=str(payment_id),
        staff_id=str(staff_id),
        total_reversed_cents=total_reversed_cents,
        active_entries=len(active_entries),
        passive_entries=len(passive_entries),
        purchases_reversed=purchases_reversed,
        reason=reason,
    )

    return {
        "payment_id": payment_id,
        "total_reversed_cents": total_reversed_cents,
        "active_entries_reversed": len(active_entries),
        "passive_entries_reversed": len(passive_entries),
        "purchases_reversed": purchases_reversed,
        "tranches_unwound": tranches_unwound,
        "affected_user_ids": list(affected_user_ids),
    }
