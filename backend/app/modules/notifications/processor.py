# =============================================================================
# CBSHOME Backend -- Notification Processor (Sprint 8.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Three-stage pipeline for pending notifications:
#     1. resolve  -- expand targets into deliveries
#     2. deliver  -- call channel formatters
#     3. rollup   -- update notification status from delivery statuses
#
#   Cleanup: delete expired notifications that have been delivered.
#
# CALLED BY:
#   worker.py (run_notification_batch) -- each notification processed
#   in its own session/transaction.
#
# EXPIRE LOGIC:
#   Notifications with expiry_at < now() are marked expired BEFORE
#   the pipeline runs. This prevents delivering stale notifications.
# =============================================================================

from datetime import datetime, UTC

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.constants import DeliveryStatus, NotificationStatus
from app.modules.notifications.models import Notification, NotificationDelivery
from app.modules.notifications.service import (
    deliver_notification,
    resolve_notification,
    rollup_notification,
)

logger = structlog.get_logger()


async def process_pending_notifications(session: AsyncSession) -> int:
    """Process all pending notifications that are ready to send.

    Pipeline per notification: resolve -> deliver -> rollup.

    Args:
        session: Active DB session (caller commits per notification).

    Returns:
        Number of notifications processed.
    """
    now = datetime.now(UTC)

    # -- Step 0: Expire overdue notifications --
    expire_stmt = (
        update(Notification)
        .where(
            Notification.status == NotificationStatus.PENDING,
            Notification.expiry_at.isnot(None),
            Notification.expiry_at < now,
        )
        .values(status=NotificationStatus.EXPIRED)
    )
    expire_result = await session.execute(expire_stmt)
    expired_count = expire_result.rowcount  # type: ignore[assignment]
    if expired_count:
        logger.info("notifications_expired", count=expired_count)

    # -- Step 1: Find pending notifications ready to process --
    stmt = (
        select(Notification)
        .where(
            Notification.status == NotificationStatus.PENDING,
            Notification.scheduled_at <= now,
        )
        .order_by(Notification.priority, Notification.scheduled_at)
    )
    result = await session.execute(stmt)
    notifications = list(result.scalars().all())

    if not notifications:
        return 0

    processed = 0
    for notification in notifications:
        try:
            # resolve
            await resolve_notification(session, notification)

            # deliver
            await deliver_notification(session, notification)

            # rollup
            await rollup_notification(session, notification)

            processed += 1
        except Exception:
            logger.exception(
                "notification_pipeline_error",
                notification_id=str(notification.id),
            )
            notification.status = NotificationStatus.FAILED

    await session.flush()

    logger.info(
        "notifications_processed",
        total=len(notifications),
        processed=processed,
    )
    return processed


async def cleanup_expired_notifications(session: AsyncSession) -> int:
    """Delete expired notifications that have been fully delivered.

    Removes notifications where:
      - expiry_at < now()
      - status in (sent, partial_sent, expired)

    Deliveries are CASCADE-deleted automatically.

    Args:
        session: Active DB session (caller commits).

    Returns:
        Number of notifications deleted.
    """
    now = datetime.now(UTC)

    stmt = (
        delete(Notification)
        .where(
            Notification.expiry_at.isnot(None),
            Notification.expiry_at < now,
            Notification.status.in_([
                NotificationStatus.SENT,
                NotificationStatus.PARTIAL_SENT,
                NotificationStatus.EXPIRED,
            ]),
        )
    )
    result = await session.execute(stmt)
    deleted = result.rowcount  # type: ignore[assignment]

    if deleted:
        logger.info("notifications_cleaned_up", count=deleted)

    return deleted
