# =============================================================================
# CBSHOME Backend -- Payment Confirmation Service (Sprint 5.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   run_confirmation_batch() -- batch UPDATE frozen -> confirmed for:
#     1. Payment (+ updated_at)
#     2. ActiveLedger
#     3. PassiveLedger
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
# =============================================================================

from datetime import UTC, datetime

import structlog
from sqlalchemy import update

from app.core.database import get_session_factory
from app.modules.ledgers.models import ActiveLedger, LedgerStatus, PassiveLedger
from app.modules.payments.constants import PaymentStatus
from app.modules.payments.models import Payment

logger = structlog.get_logger()


async def run_confirmation_batch() -> None:
    """Execute one confirmation cycle.

    Batch UPDATE in a single transaction:
      1. Payment.status frozen -> confirmed WHERE frozen_until <= now()
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
            .returning(Payment.id)
        )
        payment_result = await session.execute(payment_stmt)
        confirmed_payments = len(payment_result.all())

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

        total = confirmed_payments + confirmed_active + confirmed_passive
        if total > 0:
            logger.info(
                "confirmation_batch_completed",
                payments=confirmed_payments,
                active_entries=confirmed_active,
                passive_entries=confirmed_passive,
            )
        else:
            logger.debug("confirmation_worker_tick")
