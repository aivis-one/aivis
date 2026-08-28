# =============================================================================
# AIVIS.ONE Backend -- Withdrawal Service (Sprint 6.3, updated Sprint 6.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_withdrawal()  -- debit passive_ledger, create pending Withdrawal
#   confirm_withdrawal() -- Staff approve: pending -> confirmed -> processing
#   reject_withdrawal()  -- Staff reject: compensating ledger entry
#   complete_withdrawal()-- processing -> completed (webhook/system)
#   fail_withdrawal()    -- processing -> failed + compensating ledger entry
#   get_my_withdrawals() -- paginated list for authenticated user
#   list_all_withdrawals()-- paginated list for staff (discovery, filters)
#   get_withdrawal()     -- load single withdrawal by id
#
# LEDGER MECHANICS:
#   - create: record_passive_ledger(-amount, confirmed) -- debit immediately
#   - reject/fail: record_passive_ledger(+amount, confirmed) -- compensating
#
# CONCURRENCY:
#   - create: pg_advisory_xact_lock(user_id) serializes with purchases
#     (same lock_id as engine.py) -- prevents double-spend race condition
#   - confirm/reject/complete/fail: SELECT FOR UPDATE on Withdrawal row
#     serializes concurrent staff actions on the same withdrawal
#   - Partial unique index uq_withdrawals_user_active prevents multiple
#     active withdrawals. IntegrityError caught by constraint name.
#
# Sprint 6.4: record_transaction() for all 5 withdrawal lifecycle events.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages transaction.
# =============================================================================

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms import comms_configured
from app.core.config import settings
from app.core.constants import LedgerReason
from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import get_passive_balance, record_passive_ledger
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction
from app.modules.users.models import User
from app.modules.withdrawals.constants import (
    WithdrawalStatus,
    validate_withdrawal_status_transition,
)
from app.modules.withdrawals.models import Withdrawal

logger = structlog.get_logger()

# Batch 3 (2026-08-27), second aivis producer of notification_request (see
# comms-profile/types.yaml). Titles keyed by the withdrawal's CURRENT
# status -- confirm_withdrawal's MVP cascade means a withdrawal is never
# actually left sitting in CONFIRMED, so PROCESSING is the status a user
# is notified about, not CONFIRMED. English only: same pre-existing gap
# as the kyc.* emitter, not a new one (core/email.py has no locale
# branching either).
_WITHDRAWAL_NOTIFICATION_TITLES = {
    WithdrawalStatus.PROCESSING: "Withdrawal approved",
    WithdrawalStatus.REJECTED: "Withdrawal rejected",
    WithdrawalStatus.COMPLETED: "Withdrawal completed",
    WithdrawalStatus.FAILED: "Withdrawal failed",
}


async def _notify_withdrawal(
    session: AsyncSession,
    withdrawal: Withdrawal,
    *,
    reason: str | None = None,
) -> None:
    """Emit notification_request for a withdrawal's CURRENT status.

    Same gate as every other emitter in this tree: without a comms
    address the relay is disabled too (same empty setting), so a row
    emitted here would sit in the outbox forever with nobody to ship it.

    Each of the four call sites below reaches a status the state
    machine (constants.VALID_WITHDRAWAL_STATUS_TRANSITIONS) only ever
    lets a withdrawal enter ONCE -- PROCESSING, REJECTED, COMPLETED and
    FAILED are either reachable through exactly one inbound edge or are
    terminal with no outbound edges at all -- so
    f"withdrawal-{status}:{id}" is a safe, permanent dedup key without
    needing a transition counter.
    """
    if not comms_configured():
        return

    amount = f"{withdrawal.amount_cents / 100:,.2f}"
    if withdrawal.status == WithdrawalStatus.PROCESSING:
        body = (
            f"Your withdrawal of ${amount} has been approved and is "
            f"now processing."
        )
    elif withdrawal.status == WithdrawalStatus.REJECTED:
        body = (
            f"Your withdrawal of ${amount} was rejected: {reason}. "
            f"The amount has been returned to your balance."
        )
    elif withdrawal.status == WithdrawalStatus.COMPLETED:
        body = f"Your withdrawal of ${amount} has been sent."
    else:
        body = (
            f"Your withdrawal of ${amount} could not be completed. "
            f"The amount has been returned to your balance."
        )

    await emit_event(
        session,
        EVENT_NOTIFICATION_REQUEST,
        {
            "idempotency_key": f"withdrawal-{withdrawal.status}:{withdrawal.id}",
            "type": f"withdrawal.{withdrawal.status}",
            "target_type": "user",
            "target_value": str(withdrawal.user_id),
            "title": _WITHDRAWAL_NOTIFICATION_TITLES[withdrawal.status],
            "body": body,
        },
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_withdrawal(
    user: User,
    amount_cents: int,
    session: AsyncSession,
) -> Withdrawal:
    """Create a withdrawal request and debit passive_ledger immediately.

    Guards:
      - payout_details must be configured
      - amount within MIN/MAX bounds
      - confirmed passive balance >= amount (under advisory lock)
      - no other active withdrawal (DB constraint)

    Concurrency: pg_advisory_xact_lock serializes with purchases
    (same lock_id as engine.py) to prevent double-spend when a
    purchase and withdrawal race on the same user's balance.

    Args:
        user: Authenticated user.
        amount_cents: Amount to withdraw in cents (positive).
        session: Active DB session. Caller manages commit (P-01).

    Returns:
        Created Withdrawal (flushed, not committed).

    Raises:
        BadRequestError: Payout details missing, amount out of bounds,
            insufficient balance.
        ConflictError: Active withdrawal already exists.
    """
    # -- Guard: payout details --
    if not user.payout_details:
        raise BadRequestError("Payout details not configured")

    # -- Guard: amount bounds --
    if amount_cents < settings.min_withdrawal_cents:
        raise BadRequestError(
            f"Minimum withdrawal is {settings.min_withdrawal_cents} cents"
        )
    if amount_cents > settings.max_withdrawal_cents:
        raise BadRequestError(
            f"Maximum withdrawal is {settings.max_withdrawal_cents} cents"
        )

    # -- Advisory lock: serialize with purchases on same user --
    lock_id = user.id.int & 0x7FFFFFFFFFFFFFFF
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": lock_id},
    )

    # -- Guard: confirmed passive balance --
    balance = await get_passive_balance(session, user.id)
    confirmed = balance["confirmed"]
    if confirmed < amount_cents:
        raise BadRequestError(
            f"Insufficient confirmed passive balance: "
            f"available={confirmed}, required={amount_cents}"
        )

    # -- Snapshot payout details --
    payout_snapshot = dict(user.payout_details)

    # -- Create Withdrawal --
    withdrawal = Withdrawal(
        user_id=user.id,
        amount_cents=amount_cents,
        status=WithdrawalStatus.PENDING,
        payout_details_snapshot=payout_snapshot,
    )

    try:
        async with session.begin_nested():
            session.add(withdrawal)
            await session.flush()
    except IntegrityError as exc:
        if "uq_withdrawals_user_active" in str(exc.orig):
            raise ConflictError(
                "An active withdrawal request already exists"
            )
        raise

    await session.refresh(withdrawal)

    # -- Debit passive_ledger immediately --
    reason = LedgerReason.WITHDRAWAL.format(withdrawal_id=withdrawal.id)
    await record_passive_ledger(
        session,
        user_id=user.id,
        amount_cents=-amount_cents,
        status=LedgerStatus.CONFIRMED,
        reason=reason,
    )

    # -- Audit --
    await record_audit(
        session=session,
        event="withdrawal.created",
        actor_id=user.id,
        actor_type="user",
        target_type="withdrawal",
        target_id=withdrawal.id,
        data={"amount_cents": amount_cents},
    )

    # -- Transaction log (Sprint 6.4) --
    await record_transaction(
        session,
        user_id=user.id,
        type=TransactionType.WITHDRAWAL_CREATED,
        amount_cents=-amount_cents,
        reference_id=withdrawal.id,
        reference_type=ReferenceType.WITHDRAWAL,
        details={"status": "pending"},
    )

    logger.info(
        "withdrawal_created",
        withdrawal_id=str(withdrawal.id),
        user_id=str(user.id),
        amount_cents=amount_cents,
    )

    return withdrawal


# ---------------------------------------------------------------------------
# Staff: confirm
# ---------------------------------------------------------------------------


async def confirm_withdrawal(
    withdrawal_id: UUID,
    staff: User,
    session: AsyncSession,
) -> Withdrawal:
    """Staff approves withdrawal: pending -> confirmed -> processing.

    In MVP, confirmed -> processing happens immediately (payment provider
    stub). When a real provider is integrated, processing will be triggered
    by the provider push.

    Uses SELECT FOR UPDATE to serialize concurrent staff actions.

    Args:
        withdrawal_id: Withdrawal to confirm.
        staff: Staff user performing the action.
        session: Active DB session. Caller manages commit (P-01).

    Returns:
        Updated Withdrawal.

    Raises:
        NotFoundError: Withdrawal not found.
        BadRequestError: Invalid status transition.
    """
    withdrawal = await _load_withdrawal(withdrawal_id, session, for_update=True)

    # -- Transition: pending -> confirmed --
    validate_withdrawal_status_transition(
        withdrawal.status, WithdrawalStatus.CONFIRMED
    )
    now = datetime.now(UTC)
    withdrawal.status = WithdrawalStatus.CONFIRMED
    withdrawal.confirmed_at = now

    # -- MVP: immediately transition confirmed -> processing --
    validate_withdrawal_status_transition(
        withdrawal.status, WithdrawalStatus.PROCESSING
    )
    withdrawal.status = WithdrawalStatus.PROCESSING
    withdrawal.processing_at = now

    await session.flush()
    await session.refresh(withdrawal)

    # -- Audit --
    await record_audit(
        session=session,
        event="withdrawal.confirmed",
        actor_id=staff.id,
        actor_type="staff",
        target_type="withdrawal",
        target_id=withdrawal.id,
        data={
            "amount_cents": withdrawal.amount_cents,
            "user_id": str(withdrawal.user_id),
        },
    )

    # -- Transaction log (Sprint 6.4) --
    await record_transaction(
        session,
        user_id=withdrawal.user_id,
        type=TransactionType.WITHDRAWAL_CONFIRMED,
        amount_cents=-withdrawal.amount_cents,
        reference_id=withdrawal.id,
        reference_type=ReferenceType.WITHDRAWAL,
        details={"staff_id": str(staff.id)},
    )

    await _notify_withdrawal(session, withdrawal)

    logger.info(
        "withdrawal_confirmed",
        withdrawal_id=str(withdrawal.id),
        staff_id=str(staff.id),
    )

    return withdrawal


# ---------------------------------------------------------------------------
# Staff: reject
# ---------------------------------------------------------------------------


async def reject_withdrawal(
    withdrawal_id: UUID,
    reason: str,
    staff: User,
    session: AsyncSession,
) -> Withdrawal:
    """Staff rejects withdrawal: pending -> rejected + compensating entry.

    Compensating passive_ledger credit restores the debited amount.
    Uses SELECT FOR UPDATE to serialize concurrent staff actions.

    Args:
        withdrawal_id: Withdrawal to reject.
        reason: Rejection reason (required).
        staff: Staff user performing the action.
        session: Active DB session. Caller manages commit (P-01).

    Returns:
        Updated Withdrawal.

    Raises:
        NotFoundError: Withdrawal not found.
        BadRequestError: Invalid status transition.
    """
    withdrawal = await _load_withdrawal(withdrawal_id, session, for_update=True)

    # -- Transition: pending -> rejected --
    validate_withdrawal_status_transition(
        withdrawal.status, WithdrawalStatus.REJECTED
    )
    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.rejection_reason = reason
    withdrawal.rejected_at = datetime.now(UTC)

    await session.flush()

    # -- Compensating ledger entry (credit back) --
    reversal_reason = (
        LedgerReason.WITHDRAWAL.format(withdrawal_id=withdrawal.id)
        + ":reversal"
    )
    await record_passive_ledger(
        session,
        user_id=withdrawal.user_id,
        amount_cents=withdrawal.amount_cents,
        status=LedgerStatus.CONFIRMED,
        reason=reversal_reason,
    )

    await session.refresh(withdrawal)

    # -- Audit --
    await record_audit(
        session=session,
        event="withdrawal.rejected",
        actor_id=staff.id,
        actor_type="staff",
        target_type="withdrawal",
        target_id=withdrawal.id,
        data={
            "amount_cents": withdrawal.amount_cents,
            "user_id": str(withdrawal.user_id),
            "reason": reason,
        },
    )

    # -- Transaction log (Sprint 6.4) --
    # Round 4 (BUG-01): compensating entry. The user's funds were debited
    # at WITHDRAWAL_CREATED with -X; on reject we credit them back with
    # +X (matches passive_ledger above). Convention in transactions.service:
    # positive=in, negative=out.
    await record_transaction(
        session,
        user_id=withdrawal.user_id,
        type=TransactionType.WITHDRAWAL_REJECTED,
        amount_cents=withdrawal.amount_cents,
        reference_id=withdrawal.id,
        reference_type=ReferenceType.WITHDRAWAL,
        details={"reason": reason, "staff_id": str(staff.id)},
    )

    await _notify_withdrawal(session, withdrawal, reason=reason)

    logger.info(
        "withdrawal_rejected",
        withdrawal_id=str(withdrawal.id),
        staff_id=str(staff.id),
        reason=reason,
    )

    return withdrawal


# ---------------------------------------------------------------------------
# System: complete
# ---------------------------------------------------------------------------


async def complete_withdrawal(
    withdrawal_id: UUID,
    session: AsyncSession,
) -> Withdrawal:
    """Mark withdrawal as completed: processing -> completed.

    Called by payment provider webhook or system process after
    payout is confirmed. Uses SELECT FOR UPDATE to serialize.

    Args:
        withdrawal_id: Withdrawal to complete.
        session: Active DB session. Caller manages commit (P-01).

    Returns:
        Updated Withdrawal.

    Raises:
        NotFoundError: Withdrawal not found.
        BadRequestError: Invalid status transition.
    """
    withdrawal = await _load_withdrawal(withdrawal_id, session, for_update=True)

    validate_withdrawal_status_transition(
        withdrawal.status, WithdrawalStatus.COMPLETED
    )
    withdrawal.status = WithdrawalStatus.COMPLETED
    withdrawal.completed_at = datetime.now(UTC)

    await session.flush()
    await session.refresh(withdrawal)

    await record_audit(
        session=session,
        event="withdrawal.completed",
        actor_id=withdrawal.user_id,
        actor_type="system",
        target_type="withdrawal",
        target_id=withdrawal.id,
        data={"amount_cents": withdrawal.amount_cents},
    )

    # -- Transaction log (Sprint 6.4) --
    await record_transaction(
        session,
        user_id=withdrawal.user_id,
        type=TransactionType.WITHDRAWAL_COMPLETED,
        amount_cents=-withdrawal.amount_cents,
        reference_id=withdrawal.id,
        reference_type=ReferenceType.WITHDRAWAL,
    )

    await _notify_withdrawal(session, withdrawal)

    logger.info(
        "withdrawal_completed",
        withdrawal_id=str(withdrawal.id),
    )

    return withdrawal


# ---------------------------------------------------------------------------
# System: fail
# ---------------------------------------------------------------------------


async def fail_withdrawal(
    withdrawal_id: UUID,
    session: AsyncSession,
) -> Withdrawal:
    """Mark withdrawal as failed: processing -> failed + compensating entry.

    Called by payment provider webhook when payout is rejected.
    Uses SELECT FOR UPDATE to serialize.

    Args:
        withdrawal_id: Withdrawal to fail.
        session: Active DB session. Caller manages commit (P-01).

    Returns:
        Updated Withdrawal.

    Raises:
        NotFoundError: Withdrawal not found.
        BadRequestError: Invalid status transition.
    """
    withdrawal = await _load_withdrawal(withdrawal_id, session, for_update=True)

    validate_withdrawal_status_transition(
        withdrawal.status, WithdrawalStatus.FAILED
    )
    withdrawal.status = WithdrawalStatus.FAILED
    withdrawal.failed_at = datetime.now(UTC)

    await session.flush()

    # -- Compensating ledger entry (credit back) --
    reversal_reason = (
        LedgerReason.WITHDRAWAL.format(withdrawal_id=withdrawal.id)
        + ":reversal"
    )
    await record_passive_ledger(
        session,
        user_id=withdrawal.user_id,
        amount_cents=withdrawal.amount_cents,
        status=LedgerStatus.CONFIRMED,
        reason=reversal_reason,
    )

    await session.refresh(withdrawal)

    await record_audit(
        session=session,
        event="withdrawal.failed",
        actor_id=withdrawal.user_id,
        actor_type="system",
        target_type="withdrawal",
        target_id=withdrawal.id,
        data={"amount_cents": withdrawal.amount_cents},
    )

    # -- Transaction log (Sprint 6.4) --
    # Round 4 (BUG-01): compensating entry. Symmetric to reject_withdrawal
    # above -- payout failed at the provider side, the funds debited at
    # WITHDRAWAL_CREATED are credited back with +X.
    await record_transaction(
        session,
        user_id=withdrawal.user_id,
        type=TransactionType.WITHDRAWAL_FAILED,
        amount_cents=withdrawal.amount_cents,
        reference_id=withdrawal.id,
        reference_type=ReferenceType.WITHDRAWAL,
    )

    await _notify_withdrawal(session, withdrawal)

    logger.info(
        "withdrawal_failed",
        withdrawal_id=str(withdrawal.id),
    )

    return withdrawal


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


async def get_my_withdrawals(
    user_id: UUID,
    session: AsyncSession,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Withdrawal], int]:
    """Get paginated withdrawal history for a user.

    Returns:
        (withdrawals, total_count) tuple.
    """
    # Count.
    count_stmt = (
        select(func.count())
        .select_from(Withdrawal)
        .where(Withdrawal.user_id == user_id)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Items.
    stmt = (
        select(Withdrawal)
        .where(Withdrawal.user_id == user_id)
        .order_by(Withdrawal.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def list_all_withdrawals(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
    status: str | None = None,
    user_id: UUID | None = None,
) -> tuple[list[Withdrawal], int]:
    """List all withdrawals for staff view with optional filters.

    Mirrors payments/service.py's list_all_payments() query shape
    (count + offset/limit, ordered by created_at desc) -- this is the
    staff-facing discovery endpoint that confirm/reject need: without
    it, staff have no way to find a pending withdrawal_id to act on.

    Args:
        session: Active DB session (reader is fine -- staff list is
            read-only).
        page: Page number (1-based).
        per_page: Items per page.
        status: Optional status filter (pending, confirmed, processing,
            completed, rejected, failed).
        user_id: Optional user filter.

    Returns:
        (withdrawals, total_count).
    """
    # Build filters.
    filters = []
    if status is not None:
        filters.append(Withdrawal.status == status)
    if user_id is not None:
        filters.append(Withdrawal.user_id == user_id)

    # Count total.
    count_stmt = select(func.count()).select_from(Withdrawal)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(Withdrawal)
        .order_by(Withdrawal.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    if filters:
        stmt = stmt.where(*filters)

    result = await session.execute(stmt)
    withdrawals = list(result.scalars().all())

    return withdrawals, total


async def get_withdrawal(
    withdrawal_id: UUID,
    session: AsyncSession,
) -> Withdrawal:
    """Load a single withdrawal by ID.

    Raises:
        NotFoundError: Withdrawal not found.
    """
    return await _load_withdrawal(withdrawal_id, session)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_withdrawal(
    withdrawal_id: UUID,
    session: AsyncSession,
    for_update: bool = False,
) -> Withdrawal:
    """Load withdrawal by ID or raise NotFoundError.

    Args:
        withdrawal_id: Withdrawal UUID.
        session: Active DB session.
        for_update: If True, use SELECT FOR UPDATE to serialize
            concurrent mutations on the same row.
    """
    stmt = select(Withdrawal).where(Withdrawal.id == withdrawal_id)
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    withdrawal = result.scalar_one_or_none()

    if withdrawal is None:
        raise NotFoundError("Withdrawal not found")

    return withdrawal
