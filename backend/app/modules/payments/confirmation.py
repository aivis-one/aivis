# =============================================================================
# CBSHOME Backend -- Payment Confirmation Service (Sprint 5.3, updated 6.4)
# =============================================================================
#
# RESPONSIBILITIES:
#   run_confirmation_batch() -- batch UPDATE frozen -> confirmed for:
#     1. Payment (+ updated_at)
#     2. ActiveLedger
#     3. PassiveLedger
#   + write deposit:confirmed transaction log entries (Sprint 6.4)
#
# ALGORITHM (from CBSHOME-Financial-System.md section 5.4):
#   SELECT entries WHERE status=frozen AND frozen_until <= now()
#   UPDATE status=confirmed
#
# Each table is updated independently -- a ledger entry's frozen_until
# is its own, not inherited from the parent Payment.
#
# SESSION:
#   Creates its own session via get_session_factory() -- runs inside
#   a background asyncio.Task, not inside a request context.
#   Commits at the end of each batch.
#
# ORM NOTE (S53-WARN-2):
#   Payment.updated_at uses onupdate=func.now(), but bulk update()
#   bypasses ORM events. We set updated_at explicitly in .values().
#   ActiveLedger and PassiveLedger have no updated_at -- not affected.
#
# Sprint 6.4:
#   After confirming payments, write deposit:confirmed Transaction entries
#   for each confirmed payment. RETURNING includes user_id, amount_cents, id
#   so we can create transaction log entries without extra queries.
# =============================================================================

from datetime import UTC, datetime

import structlog
from sqlalchemy import update

from app.core.database import get_session_factory
from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.models import Payment
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.models import Transaction

logger = structlog.get_logger()


async def run_confirmation_batch() -> None:
    """Execute one confirmation cycle.

    Batch UPDATE in a single transaction:
      1. Payment.status frozen -> confirmed WHERE frozen_until <= now()
         + write deposit:confirmed transaction log entries
      2. ActiveLedger.status frozen -> confirmed WHERE frozen_until <= now()
      3. PassiveLedger.status frozen -> confirmed WHERE frozen_until <= now()
    """
    factory = get_session_factory()
    async with factory() as session:
        now = datetime.now(UTC)

        # 1. Confirm payments (explicit updated_at -- onupdate skipped by bulk).
        payment_stmt = (
            update(Payment)
            .where(
                Payment.status == PaymentStatus.FROZEN,
                Payment.frozen_until <= now,
            )
            .values(status=PaymentStatus.CONFIRMED, updated_at=now)
            .returning(Payment.id, Payment.user_id, Payment.amount_cents)
        )
        payment_result = await session.execute(payment_stmt)
        confirmed_payments = payment_result.all()

        # Sprint 6.4: write deposit:confirmed transaction log entries.
        for row in confirmed_payments:
            txn_entry = Transaction(
                user_id=row.user_id,
                type=TransactionType.DEPOSIT_CONFIRMED,
                amount_cents=row.amount_cents,
                currency="USD",
                reference_id=row.id,
                reference_type=ReferenceType.PAYMENT,
            )
            session.add(txn_entry)

        if confirmed_payments:
            await session.flush()

        # 2. Confirm active_ledger entries (no updated_at column).
        active_stmt = (
            update(ActiveLedger)
            .where(
                ActiveLedger.status == LedgerStatus.FROZEN,
                ActiveLedger.frozen_until <= now,
            )
            .values(status=LedgerStatus.CONFIRMED)
            .returning(ActiveLedger.id)
        )
        active_result = await session.execute(active_stmt)
        confirmed_active = len(active_result.all())

        # 3. Confirm passive_ledger entries (no updated_at column).
        passive_stmt = (
            update(PassiveLedger)
            .where(
                PassiveLedger.status == LedgerStatus.FROZEN,
                PassiveLedger.frozen_until <= now,
            )
            .values(status=LedgerStatus.CONFIRMED)
            .returning(PassiveLedger.id)
        )
        passive_result = await session.execute(passive_stmt)
        confirmed_passive = len(passive_result.all())

        await session.commit()

        total = len(confirmed_payments) + confirmed_active + confirmed_passive
        if total > 0:
            logger.info(
                "confirmation_batch_completed",
                payments=len(confirmed_payments),
                active_entries=confirmed_active,
                passive_entries=confirmed_passive,
            )
        else:
            logger.debug("confirmation_worker_tick")
