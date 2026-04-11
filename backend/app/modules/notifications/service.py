# =============================================================================
# CBSHOME Backend -- Notification Service (Sprint 8.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Business logic for creating and processing notifications.
#
# FUNCTIONS:
#   create_notification()   -- create a Notification record
#   resolve_notification()  -- expand targets into NotificationDelivery rows
#   deliver_notification()  -- call formatters for pending deliveries
#   rollup_notification()   -- update Notification.status from delivery statuses
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

from datetime import datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.notifications.constants import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationStatus,
    NotificationType,
    TargetType,
)
from app.modules.notifications.formatters import get_formatter
from app.modules.notifications.models import Notification, NotificationDelivery
from app.modules.notifications.resolver import resolve_targets

logger = structlog.get_logger()


async def create_notification(
    session: AsyncSession,
    *,
    type: str,
    title: str,
    body: str,
    target_type: str,
    target_value: str,
    channels: list[str] | None = None,
    action_data: dict | None = None,
    priority: int = 5,
    scheduled_at: datetime | None = None,
    expiry_at: datetime | None = None,
) -> Notification:
    """Create a new Notification record.

    Args:
        session: Active DB session (caller commits).
        type: NotificationType value.
        title: Notification title.
        body: Notification body text.
        target_type: TargetType value (user, role, all).
        target_value: Target specifier (e.g. "user:<uuid>", "role:agent", "*").
        channels: Delivery channels. Defaults to ["in_app"].
        action_data: Optional JSONB action payload.
        priority: 1=highest, 5=default.
        scheduled_at: When to process. Defaults to now.
        expiry_at: Optional TTL deadline.

    Returns:
        The created Notification (flushed, not committed).
    """
    if channels is None:
        channels = [DeliveryChannel.IN_APP]

    if scheduled_at is None:
        scheduled_at = datetime.now(UTC)

    notification = Notification(
        type=type,
        title=title,
        body=body,
        target_type=target_type,
        target_value=target_value,
        action_data=action_data,
        priority=priority,
        scheduled_at=scheduled_at,
        expiry_at=expiry_at,
        status=NotificationStatus.PENDING,
    )
    session.add(notification)
    await session.flush()

    # Store channels in action_data for resolve stage.
    # This avoids adding a separate column -- channels are immutable after creation.
    if notification.action_data is None:
        notification.action_data = {"_channels": channels}
    else:
        notification.action_data = {**notification.action_data, "_channels": channels}

    logger.info(
        "notification_created",
        notification_id=str(notification.id),
        type=type,
        target=f"{target_type}:{target_value}",
        channels=channels,
    )

    return notification


async def resolve_notification(
    session: AsyncSession,
    notification: Notification,
) -> list[NotificationDelivery]:
    """Expand notification targets into NotificationDelivery rows.

    Transitions notification status: pending -> processing.

    Args:
        session: Active DB session (caller commits).
        notification: The notification to resolve.

    Returns:
        List of created NotificationDelivery objects.
    """
    # Resolve target users.
    user_ids = await resolve_targets(
        session,
        notification.target_type,
        notification.target_value,
    )

    if not user_ids:
        notification.status = NotificationStatus.FAILED
        logger.warning(
            "notification_no_targets",
            notification_id=str(notification.id),
        )
        return []

    # Get channels from action_data.
    channels = (notification.action_data or {}).get(
        "_channels", [DeliveryChannel.IN_APP]
    )

    # Create delivery records.
    deliveries: list[NotificationDelivery] = []
    for user_id in user_ids:
        for channel in channels:
            delivery = NotificationDelivery(
                notification_id=notification.id,
                user_id=user_id,
                channel=channel,
                status=DeliveryStatus.PENDING,
            )
            session.add(delivery)
            deliveries.append(delivery)

    notification.status = NotificationStatus.PROCESSING
    await session.flush()

    logger.info(
        "notification_resolved",
        notification_id=str(notification.id),
        users=len(user_ids),
        channels=len(channels),
        deliveries=len(deliveries),
    )

    return deliveries


async def deliver_notification(
    session: AsyncSession,
    notification: Notification,
) -> None:
    """Deliver pending deliveries for a notification via channel formatters.

    Args:
        session: Active DB session (caller commits).
        notification: The notification whose deliveries to process.
    """
    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notification.id,
        NotificationDelivery.status == DeliveryStatus.PENDING,
    )
    result = await session.execute(stmt)
    deliveries = list(result.scalars().all())

    for delivery in deliveries:
        formatter = get_formatter(delivery.channel)
        delivery.attempts += 1

        try:
            success = await formatter.deliver(notification, delivery)
        except Exception as exc:
            success = False
            delivery.error_message = str(exc)[:2000]
            logger.exception(
                "delivery_error",
                delivery_id=str(delivery.id),
                channel=delivery.channel,
            )

        if success:
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = datetime.now(UTC)
        else:
            max_attempts = settings.notification_max_delivery_attempts
            if delivery.attempts >= max_attempts:
                delivery.status = DeliveryStatus.FAILED

    await session.flush()


async def rollup_notification(
    session: AsyncSession,
    notification: Notification,
) -> None:
    """Update Notification.status based on delivery statuses.

    Rules:
      - All sent         -> sent
      - All failed       -> failed
      - Mix sent+failed  -> partial_sent
      - Any pending      -> stays processing (not all delivered yet)

    Args:
        session: Active DB session (caller commits).
        notification: The notification to roll up.
    """
    stmt = select(NotificationDelivery.status).where(
        NotificationDelivery.notification_id == notification.id,
    )
    result = await session.execute(stmt)
    statuses = {row[0] for row in result.all()}

    if not statuses:
        # No deliveries at all -- should not happen after resolve.
        notification.status = NotificationStatus.FAILED
        return

    has_pending = DeliveryStatus.PENDING in statuses
    has_sent = DeliveryStatus.SENT in statuses
    has_failed = DeliveryStatus.FAILED in statuses

    if has_pending:
        # Still processing -- don't change status.
        return

    if has_sent and not has_failed:
        notification.status = NotificationStatus.SENT
    elif has_failed and not has_sent:
        notification.status = NotificationStatus.FAILED
    else:
        notification.status = NotificationStatus.PARTIAL_SENT

    await session.flush()

    logger.info(
        "notification_rollup",
        notification_id=str(notification.id),
        status=notification.status,
    )
