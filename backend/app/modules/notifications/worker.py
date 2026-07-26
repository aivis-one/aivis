# =============================================================================
# AIVIS.ONE Backend -- Notification Worker (Sprint 8.1, fix review)
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
# SESSION MANAGEMENT (fix review):
#   Processor manages its own sessions internally -- each notification
#   gets its own session/transaction. Worker is just an orchestrator.
# =============================================================================

import structlog

from app.modules.notifications.processor import (
    cleanup_expired_notifications,
    process_pending_notifications,
)

logger = structlog.get_logger()


async def run_notification_batch() -> None:
    """Process pending notifications and clean up expired ones.

    Called once per cycle by the notification daemon in main.py.
    Processor handles session management internally.
    """
    await process_pending_notifications()
    await cleanup_expired_notifications()
