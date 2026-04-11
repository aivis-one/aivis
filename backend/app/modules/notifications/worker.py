# =============================================================================
# CBSHOME Backend -- Notification Worker (Sprint 8.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Batch processing for notification daemon. Called every
#   NOTIFICATION_WORKER_INTERVAL_MINUTES by the asyncio.Task in main.py.
#
# ALGORITHM:
#   1. Process pending notifications (resolve -> deliver -> rollup)
#   2. Cleanup expired delivered notifications
#
# SESSION MANAGEMENT:
#   Uses get_session_factory() for its own session -- same pattern as
#   confirmation_worker and installment_worker. Each batch runs in
#   a single transaction.
# =============================================================================

import structlog

from app.core.database import get_session_factory
from app.modules.notifications.processor import (
    cleanup_expired_notifications,
    process_pending_notifications,
)

logger = structlog.get_logger()


async def run_notification_batch() -> None:
    """Process pending notifications and clean up expired ones.

    Called once per cycle by the notification daemon in main.py.
    Each phase runs in its own session/transaction.
    """
    factory = get_session_factory()

    # -- Phase 1: Process pending notifications --
    async with factory() as session:
        try:
            await process_pending_notifications(session)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("notification_batch_process_error")

    # -- Phase 2: Cleanup expired notifications --
    async with factory() as session:
        try:
            await cleanup_expired_notifications(session)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("notification_batch_cleanup_error")
