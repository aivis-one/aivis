# =============================================================================
# CBSHOME Backend -- Notification Service (Sprint 8.1 + 8.2)
# =============================================================================
#
# RESPONSIBILITY:
#   Business logic for creating and processing notifications.
#
# FUNCTIONS:
#   create_notification()   -- create a Notification record (with validation)
#   resolve_notification()  -- expand targets into NotificationDelivery rows
#   deliver_notification()  -- call formatters for pending deliveries
#   rollup_notification()   -- update Notification.status from delivery statuses
#
# SPRINT 8.2:
#   - deliver_notification batch-loads Users for credentials + language
#   - asyncio.wait_for timeout on formatter.deliver() (TD-055)
#   - PermanentDeliveryError -> immediate FAILED without incrementing attempts
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

import asyncio
from datetime import datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.modules.notifications.constants import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationStatus,
    NotificationType,
    TargetType,
)
from app.modules.notifications.formatters import (
    PermanentDeliveryError,
    get_formatter,
)
from app.modules.notifications.models import Notification, NotificationDelivery
from app.modules.notifications.resolver import resolve_targets
from app.modules.users.models import User

logger = structlog.get_logger()

# Valid enum values for input validation.
_VALID_TYPES = frozenset(e.value for e in NotificationType)
_VALID_TARGET_TYPES = frozenset(e.value for e in TargetType)
_VALID_CHANNELS = frozenset(e.value for e in DeliveryChannel)

# Timeout for a single formatter.deliver() call (TD-055).
_DELIVER_TIMEOUT_SECONDS = 30


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

    Raises:
        BadRequestError: On invalid type, target_type, or channel values.
    """
    # -- Validate enum values --
    if type not in _VALID_TYPES:
        raise BadRequestError(
            f"Invalid notification type: {type}. "
            f"Valid: {', '.join(sorted(_VALID_TYPES))}"
        )

    if target_type not in _VALID_TARGET_TYPES:
        raise BadRequestError(
            f"Invalid target_type: {target_type}. "
            f"Valid: {', '.join(sorted(_VALID_TARGET_TYPES))}"
        )

    if channels is None:
        channels = [DeliveryChannel.IN_APP]

    invalid_channels = set(channels) - _VALID_CHANNELS
    if invalid_channels:
        raise BadRequestError(
            f"Invalid channels: {invalid_channels}. "
            f"Valid: {', '.join(sorted(_VALID_CHANNELS))}"
        )

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

    Idempotent: if deliveries already exist (PROCESSING retry),
    skips resolve and returns existing deliveries.

    Transitions notification status: pending -> processing.

    Args:
        session: Active DB session (caller commits).
        notification: The notification to resolve.

    Returns:
        List of NotificationDelivery objects (created or existing).
    """
    # -- Idempotency: check if already resolved --
    existing_stmt = select(func.count()).where(
        NotificationDelivery.notification_id == notification.id,
    )
    existing_result = await session.execute(existing_stmt)
    existing_count = existing_result.scalar_one()

    if existing_count > 0:
        # Already resolved -- return existing deliveries.
        stmt = select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notification.id,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # -- Resolve target users --
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

    Sprint 8.2 changes:
      - Batch-loads User objects for credentials and language.
      - Passes User to formatter.deliver().
      - asyncio.wait_for with timeout (TD-055).
      - PermanentDeliveryError -> immediate FAILED, no attempts increment.

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

    if not deliveries:
        return

    # -- Batch load users for all pending deliveries --
    user_ids: set[UUID] = {d.user_id for d in deliveries}
    user_stmt = select(User).where(User.id.in_(user_ids))
    user_result = await session.execute(user_stmt)
    users_by_id: dict[UUID, User] = {
        u.id: u for u in user_result.scalars().all()
    }

    for delivery in deliveries:
        user = users_by_id.get(delivery.user_id)
        if user is None:
            # User deleted between resolve and deliver.
            delivery.status = DeliveryStatus.FAILED
            delivery.error_message = "User not found"
            logger.warning(
                "delivery_user_not_found",
                delivery_id=str(delivery.id),
                user_id=str(delivery.user_id),
            )
            continue

        formatter = get_formatter(delivery.channel)

        try:
            success = await asyncio.wait_for(
                formatter.deliver(notification, delivery, user),
                timeout=_DELIVER_TIMEOUT_SECONDS,
            )
            delivery.attempts += 1
        except PermanentDeliveryError as exc:
            # Permanent failure -- mark as failed immediately,
            # do NOT increment attempts (no point retrying).
            delivery.status = DeliveryStatus.FAILED
            delivery.error_message = str(exc)[:2000]
            logger.warning(
                "delivery_permanent_failure",
                delivery_id=str(delivery.id),
                channel=delivery.channel,
                error=str(exc)[:200],
            )
            continue
        except asyncio.TimeoutError:
            # Timeout -- transient, increment attempts.
            delivery.attempts += 1
            delivery.error_message = (
                f"Timeout after {_DELIVER_TIMEOUT_SECONDS}s"
            )
            success = False
            logger.warning(
                "delivery_timeout",
                delivery_id=str(delivery.id),
                channel=delivery.channel,
                timeout=_DELIVER_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            # Unexpected error -- transient, increment attempts.
            delivery.attempts += 1
            delivery.error_message = str(exc)[:2000]
            success = False
            logger.exception(
                "delivery_error",
                delivery_id=str(delivery.id),
                channel=delivery.channel,
            )

        if success:
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = datetime.now(UTC)
        elif delivery.status != DeliveryStatus.FAILED:
            # Transient failure -- check max attempts.
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
