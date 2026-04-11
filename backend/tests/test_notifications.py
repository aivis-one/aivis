# =============================================================================
# CBSHOME Backend -- Notification Tests (Sprint 8.1, fix review)
# =============================================================================
#
# Tests cover:
#   1:  create_notification -> Notification in DB with correct fields
#   2:  create_notification default channels -> ["in_app"]
#   3:  create_notification custom channels -> stored in action_data
#   4:  create_notification invalid type -> BadRequestError
#   5:  create_notification invalid channel -> BadRequestError
#   6:  resolve_notification user target -> 1 delivery
#   7:  resolve_notification role target -> N deliveries
#   8:  resolve_notification all target -> all active non-platform users
#   9:  resolve_notification inactive user -> 0 deliveries
#   10: deliver_notification with StubFormatter -> all deliveries sent
#   11: rollup all sent -> notification status=sent
#   12: rollup all failed -> notification status=failed
#   13: rollup mix -> notification status=partial_sent
#   14: rollup with pending -> stays processing
#   15: process_pending_notifications full pipeline -> end-to-end
#   16: cleanup_expired_notifications -> expired+sent deleted
#   17: retry: PROCESSING notification re-processed on next cycle
#   18: scheduled future notification -> not processed yet
#
# Email prefix: "s81n_" -- unique to this test file.
# =============================================================================

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, UTC
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.modules.notifications.constants import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationStatus,
    NotificationType,
    TargetType,
)
from app.modules.notifications.models import Notification, NotificationDelivery
from app.modules.notifications.processor import (
    cleanup_expired_notifications,
    process_pending_notifications,
)
from app.modules.notifications.service import (
    create_notification,
    deliver_notification,
    resolve_notification,
    rollup_notification,
)
from tests.helpers import (
    auth_headers,
    cleanup_test_users,
    register_user,
)

EMAIL_PREFIX = "s81n_"


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users and notifications before and after each test."""
    await _cleanup_notifications(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)
    yield
    await _cleanup_notifications(db_session)
    await cleanup_test_users(db_session, EMAIL_PREFIX)


async def _cleanup_notifications(session: AsyncSession) -> None:
    """Delete all test notifications (by title prefix)."""
    from sqlalchemy import delete

    stmt = select(Notification.id).where(
        Notification.title.startswith("Test:")
    )
    result = await session.execute(stmt)
    notif_ids = [row[0] for row in result.all()]

    if notif_ids:
        await session.execute(
            delete(NotificationDelivery).where(
                NotificationDelivery.notification_id.in_(notif_ids)
            )
        )
        await session.execute(
            delete(Notification).where(Notification.id.in_(notif_ids))
        )
        await session.commit()


async def _create_investor(
    client: AsyncClient, suffix: str
) -> tuple[UUID, str]:
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return UUID(data["user"]["id"]), data["session_token"]


# ---------------------------------------------------------------------------
# 1: create_notification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_notification(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_notification -> record in DB with correct fields."""
    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: system alert",
        body="Something happened",
        target_type=TargetType.ALL,
        target_value="*",
        priority=1,
    )
    await db_session.commit()

    assert notif.id is not None
    assert notif.type == NotificationType.SYSTEM
    assert notif.title == "Test: system alert"
    assert notif.status == NotificationStatus.PENDING
    assert notif.priority == 1


# ---------------------------------------------------------------------------
# 2: default channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_notification_default_channels(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Default channels -> ['in_app'] stored in action_data."""
    notif = await create_notification(
        db_session,
        type=NotificationType.NEWS,
        title="Test: default channels",
        body="body",
        target_type=TargetType.ALL,
        target_value="*",
    )
    await db_session.commit()

    assert notif.action_data["_channels"] == [DeliveryChannel.IN_APP]


# ---------------------------------------------------------------------------
# 3: custom channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_notification_custom_channels(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Custom channels stored in action_data."""
    channels = [DeliveryChannel.TELEGRAM, DeliveryChannel.EMAIL]
    notif = await create_notification(
        db_session,
        type=NotificationType.TRANSACTION,
        title="Test: custom channels",
        body="body",
        target_type=TargetType.ALL,
        target_value="*",
        channels=channels,
        action_data={"action": "open_tx"},
    )
    await db_session.commit()

    assert notif.action_data["_channels"] == channels
    assert notif.action_data["action"] == "open_tx"


# ---------------------------------------------------------------------------
# 4: invalid type -> BadRequestError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_notification_invalid_type(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Invalid notification type -> BadRequestError."""
    with pytest.raises(BadRequestError, match="Invalid notification type"):
        await create_notification(
            db_session,
            type="unknown_type",
            title="Test: invalid type",
            body="body",
            target_type=TargetType.ALL,
            target_value="*",
        )


# ---------------------------------------------------------------------------
# 5: invalid channel -> BadRequestError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_notification_invalid_channel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Invalid channel -> BadRequestError."""
    with pytest.raises(BadRequestError, match="Invalid channels"):
        await create_notification(
            db_session,
            type=NotificationType.SYSTEM,
            title="Test: invalid channel",
            body="body",
            target_type=TargetType.ALL,
            target_value="*",
            channels=["sms"],
        )


# ---------------------------------------------------------------------------
# 6: resolve user target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_user_target(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """resolve_notification with user target -> 1 delivery."""
    user_id, _ = await _create_investor(client, "resolve1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: resolve user",
        body="hello",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    deliveries = await resolve_notification(db_session, notif)
    await db_session.commit()

    assert len(deliveries) == 1
    assert deliveries[0].user_id == user_id
    assert deliveries[0].channel == DeliveryChannel.IN_APP
    assert notif.status == NotificationStatus.PROCESSING


# ---------------------------------------------------------------------------
# 7: resolve role target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_role_target(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """resolve_notification with role:investor -> deliveries for investors."""
    await _create_investor(client, "role1")
    await _create_investor(client, "role2")

    notif = await create_notification(
        db_session,
        type=NotificationType.NEWS,
        title="Test: resolve role",
        body="news for investors",
        target_type=TargetType.ROLE,
        target_value="role:investor",
    )
    await db_session.commit()

    deliveries = await resolve_notification(db_session, notif)
    await db_session.commit()

    assert len(deliveries) >= 2
    assert notif.status == NotificationStatus.PROCESSING


# ---------------------------------------------------------------------------
# 8: resolve all target
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_all_target(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """resolve_notification with all target -> all active non-platform."""
    await _create_investor(client, "all1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: resolve all",
        body="broadcast",
        target_type=TargetType.ALL,
        target_value="*",
    )
    await db_session.commit()

    deliveries = await resolve_notification(db_session, notif)
    await db_session.commit()

    assert len(deliveries) >= 1

    from app.modules.users.models import User, UserRole
    platform_stmt = select(User.id).where(User.role == UserRole.PLATFORM)
    platform_result = await db_session.execute(platform_stmt)
    platform_ids = {row[0] for row in platform_result.all()}

    delivery_user_ids = {d.user_id for d in deliveries}
    assert not delivery_user_ids.intersection(platform_ids)


# ---------------------------------------------------------------------------
# 9: resolve inactive user -> 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_inactive_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Inactive user not resolved."""
    user_id, _ = await _create_investor(client, "inactive1")

    from app.modules.users.models import User
    stmt = select(User).where(User.id == user_id)
    result = await db_session.execute(stmt)
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: inactive user",
        body="should not deliver",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    deliveries = await resolve_notification(db_session, notif)
    await db_session.commit()

    assert len(deliveries) == 0
    assert notif.status == NotificationStatus.FAILED


# ---------------------------------------------------------------------------
# 10: deliver with StubFormatter -> all sent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_stub_formatter(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """StubFormatter delivers all -> status=sent, sent_at set."""
    user_id, _ = await _create_investor(client, "deliver1")

    notif = await create_notification(
        db_session,
        type=NotificationType.TRANSACTION,
        title="Test: deliver stub",
        body="tx confirmed",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await deliver_notification(db_session, notif)
    await db_session.commit()

    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id
    )
    result = await db_session.execute(stmt)
    delivery = result.scalar_one()

    assert delivery.status == DeliveryStatus.SENT
    assert delivery.sent_at is not None
    assert delivery.attempts == 1


# ---------------------------------------------------------------------------
# 11: rollup all sent -> sent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollup_all_sent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """All deliveries sent -> notification status=sent."""
    user_id, _ = await _create_investor(client, "rollup1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: rollup sent",
        body="body",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await deliver_notification(db_session, notif)
    await rollup_notification(db_session, notif)
    await db_session.commit()

    assert notif.status == NotificationStatus.SENT


# ---------------------------------------------------------------------------
# 12: rollup all failed -> failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollup_all_failed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """All deliveries failed -> notification status=failed."""
    user_id, _ = await _create_investor(client, "rollup2")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: rollup failed",
        body="body",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id
    )
    result = await db_session.execute(stmt)
    delivery = result.scalar_one()
    delivery.status = DeliveryStatus.FAILED
    await db_session.commit()

    await rollup_notification(db_session, notif)
    await db_session.commit()

    assert notif.status == NotificationStatus.FAILED


# ---------------------------------------------------------------------------
# 13: rollup mix -> partial_sent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollup_partial_sent(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Mix of sent + failed -> notification status=partial_sent."""
    user_id, _ = await _create_investor(client, "rollup3")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: rollup partial",
        body="body",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
        channels=[DeliveryChannel.IN_APP, DeliveryChannel.EMAIL],
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id
    ).order_by(NotificationDelivery.channel)
    result = await db_session.execute(stmt)
    deliveries = list(result.scalars().all())

    deliveries[0].status = DeliveryStatus.SENT
    deliveries[0].sent_at = datetime.now(UTC)
    deliveries[1].status = DeliveryStatus.FAILED
    await db_session.commit()

    await rollup_notification(db_session, notif)
    await db_session.commit()

    assert notif.status == NotificationStatus.PARTIAL_SENT


# ---------------------------------------------------------------------------
# 14: rollup with pending -> stays processing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollup_with_pending_stays_processing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Delivery still pending -> notification stays processing."""
    user_id, _ = await _create_investor(client, "rollup4")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: rollup pending",
        body="body",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    await rollup_notification(db_session, notif)
    await db_session.commit()

    assert notif.status == NotificationStatus.PROCESSING


# ---------------------------------------------------------------------------
# 15: process_pending_notifications end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_pending_full_pipeline(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Full pipeline: pending -> processing -> sent."""
    user_id, _ = await _create_investor(client, "pipe1")

    notif = await create_notification(
        db_session,
        type=NotificationType.COMMISSION,
        title="Test: pipeline",
        body="commission earned",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    # Processor manages its own sessions.
    processed = await process_pending_notifications()

    assert processed >= 1

    # Reload notification in our session.
    db_session.expire_all()
    stmt = select(Notification).where(Notification.id == notif.id)
    result = await db_session.execute(stmt)
    refreshed = result.scalar_one()
    assert refreshed.status == NotificationStatus.SENT

    stmt2 = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id
    )
    result2 = await db_session.execute(stmt2)
    delivery = result2.scalar_one()
    assert delivery.status == DeliveryStatus.SENT


# ---------------------------------------------------------------------------
# 16: cleanup_expired_notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_expired_notifications(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Expired + sent notifications are deleted by cleanup."""
    user_id, _ = await _create_investor(client, "expire1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: expired cleanup",
        body="old news",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
        expiry_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await db_session.commit()

    # Processor expires it (expiry_at < now, status=pending).
    await process_pending_notifications()

    # Verify it's expired.
    db_session.expire_all()
    stmt = select(Notification).where(Notification.id == notif.id)
    result = await db_session.execute(stmt)
    refreshed = result.scalar_one()
    assert refreshed.status == NotificationStatus.EXPIRED

    notif_id = notif.id

    # Cleanup should delete it.
    deleted = await cleanup_expired_notifications()

    assert deleted >= 1

    # Verify it's gone.
    db_session.expire_all()
    stmt2 = select(Notification).where(Notification.id == notif_id)
    result2 = await db_session.execute(stmt2)
    assert result2.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# 17: retry -- PROCESSING notification re-processed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_processing_notification(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PROCESSING notification with pending deliveries is retried."""
    user_id, _ = await _create_investor(client, "retry1")

    notif = await create_notification(
        db_session,
        type=NotificationType.SYSTEM,
        title="Test: retry processing",
        body="retry me",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
    )
    await db_session.commit()

    # Resolve but don't deliver -- simulate partial failure.
    await resolve_notification(db_session, notif)
    notif.status = NotificationStatus.PROCESSING
    await db_session.commit()

    # Delivery is still PENDING. Processor should pick it up.
    processed = await process_pending_notifications()

    assert processed >= 1

    # Verify notification is now SENT.
    db_session.expire_all()
    stmt = select(Notification).where(Notification.id == notif.id)
    result = await db_session.execute(stmt)
    refreshed = result.scalar_one()
    assert refreshed.status == NotificationStatus.SENT

    # Verify delivery is SENT.
    stmt2 = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif.id
    )
    result2 = await db_session.execute(stmt2)
    delivery = result2.scalar_one()
    assert delivery.status == DeliveryStatus.SENT


# ---------------------------------------------------------------------------
# 18: scheduled future notification -> not processed yet
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_future_not_processed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Notification scheduled in the future -> not processed yet."""
    user_id, _ = await _create_investor(client, "future1")

    notif = await create_notification(
        db_session,
        type=NotificationType.NEWS,
        title="Test: future scheduled",
        body="coming soon",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
        scheduled_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await db_session.commit()

    processed = await process_pending_notifications()

    # Should not be processed.
    db_session.expire_all()
    stmt = select(Notification).where(Notification.id == notif.id)
    result = await db_session.execute(stmt)
    refreshed = result.scalar_one()
    assert refreshed.status == NotificationStatus.PENDING
