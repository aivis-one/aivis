# =============================================================================
# CBSHOME Backend -- Notification Endpoint Tests (Sprint 8.3)
# =============================================================================
#
# Tests cover:
#   1:  GET /notifications -> 200, empty list (no deliveries)
#   2:  GET /notifications -> 200, returns sent deliveries with notification data
#   3:  GET /notifications?type=system -> 200, filtered by type
#   4:  GET /notifications?channel=in_app -> 200, filtered by channel
#   5:  GET /unread-count -> 200, correct count
#   6:  POST /{id}/read -> 204, sets read_at
#   7:  POST /{id}/read -> 404, wrong user
#   8:  POST /read-all -> 200, marks all, returns count
#
# Email prefix: "s83_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.constants import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationType,
    TargetType,
)
from app.modules.notifications.models import NotificationDelivery
from app.modules.notifications.service import (
    create_notification,
    deliver_notification,
    resolve_notification,
)
from tests.helpers import (
    auth_headers,
    register_user,
)

EMAIL_PREFIX = "s83_"


async def _create_investor(
    client: AsyncClient, suffix: str
) -> tuple[UUID, str]:
    """Helper: register investor, return (user_id, token)."""
    data = await register_user(
        client, email=f"{EMAIL_PREFIX}{suffix}@example.com"
    )
    return UUID(data["user"]["id"]), data["session_token"]


async def _create_sent_delivery(
    client: AsyncClient,
    db_session: AsyncSession,
    suffix: str,
    *,
    notif_type: str = NotificationType.SYSTEM,
    channels: list[str] | None = None,
) -> tuple[UUID, str, UUID]:
    """Helper: create investor + notification + resolve + deliver.

    Returns (user_id, token, notification_id).
    StubFormatter always succeeds -> delivery status=sent.
    """
    user_id, token = await _create_investor(client, suffix)

    notif = await create_notification(
        db_session,
        type=notif_type,
        title=f"Test: {suffix}",
        body=f"Body for {suffix}",
        target_type=TargetType.USER,
        target_value=f"user:{user_id}",
        channels=channels or [DeliveryChannel.IN_APP],
    )
    await db_session.commit()

    await resolve_notification(db_session, notif)
    await db_session.commit()

    await deliver_notification(db_session, notif)
    await db_session.commit()

    return user_id, token, notif.id


# ---------------------------------------------------------------------------
# 1: GET /notifications -> empty list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_notifications_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /notifications -> 200, empty list when no deliveries."""
    _, token = await _create_investor(client, "empty1")

    resp = await client.get(
        "/api/v1/notifications",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["per_page"] == 20


# ---------------------------------------------------------------------------
# 2: GET /notifications -> sent deliveries with notification data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_notifications_with_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /notifications -> 200, returns sent delivery with notification fields."""
    _, token, _ = await _create_sent_delivery(client, db_session, "list1")

    resp = await client.get(
        "/api/v1/notifications",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1

    item = body["items"][0]
    # Delivery fields.
    assert "id" in item
    assert item["channel"] == DeliveryChannel.IN_APP
    assert item["status"] == DeliveryStatus.SENT
    assert item["read_at"] is None
    assert item["sent_at"] is not None
    # Parent notification fields.
    assert item["type"] == NotificationType.SYSTEM
    assert item["title"] == "Test: list1"
    assert item["body"] == "Body for list1"
    assert "priority" in item


# ---------------------------------------------------------------------------
# 3: GET /notifications?type=system -> filtered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_notifications_filter_type(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /notifications?type=system -> only system notifications."""
    user_id, token = await _create_investor(client, "ftype1")

    # Create two notifications: system + transaction.
    for ntype, suffix in [
        (NotificationType.SYSTEM, "sys"),
        (NotificationType.TRANSACTION, "txn"),
    ]:
        notif = await create_notification(
            db_session,
            type=ntype,
            title=f"Test: ftype_{suffix}",
            body=f"Body {suffix}",
            target_type=TargetType.USER,
            target_value=f"user:{user_id}",
        )
        await db_session.commit()
        await resolve_notification(db_session, notif)
        await db_session.commit()
        await deliver_notification(db_session, notif)
        await db_session.commit()

    # Filter by system.
    resp = await client.get(
        "/api/v1/notifications?type=system",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["type"] == NotificationType.SYSTEM


# ---------------------------------------------------------------------------
# 4: GET /notifications?channel=in_app -> filtered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_notifications_filter_channel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /notifications?channel=in_app -> only in_app deliveries."""
    _, token, _ = await _create_sent_delivery(
        client, db_session, "fchan1",
        channels=[DeliveryChannel.IN_APP],
    )

    resp = await client.get(
        "/api/v1/notifications?channel=in_app",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert item["channel"] == DeliveryChannel.IN_APP


# ---------------------------------------------------------------------------
# 5: GET /unread-count -> correct count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unread_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /unread-count -> correct unread count."""
    _, token, notif_id = await _create_sent_delivery(
        client, db_session, "unread1"
    )

    # All deliveries are unread initially.
    resp = await client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1

    # Mark one as read -> count decreases.
    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif_id,
    )
    result = await db_session.execute(stmt)
    delivery = result.scalars().first()
    assert delivery is not None

    await client.post(
        f"/api/v1/notifications/{delivery.id}/read",
        headers=auth_headers(token),
    )

    resp2 = await client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["count"] == body["count"] - 1


# ---------------------------------------------------------------------------
# 6: POST /{id}/read -> 204, sets read_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_read(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /{id}/read -> 204, read_at set. Idempotent on second call."""
    _, token, notif_id = await _create_sent_delivery(
        client, db_session, "read1"
    )

    # Get delivery ID.
    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif_id,
    )
    result = await db_session.execute(stmt)
    delivery = result.scalars().first()
    assert delivery is not None
    delivery_id = delivery.id

    # Mark as read.
    resp = await client.post(
        f"/api/v1/notifications/{delivery_id}/read",
        headers=auth_headers(token),
    )
    assert resp.status_code == 204

    # Verify read_at in DB.
    db_session.expire_all()
    result2 = await db_session.execute(
        select(NotificationDelivery).where(
            NotificationDelivery.id == delivery_id,
        )
    )
    refreshed = result2.scalar_one()
    assert refreshed.read_at is not None

    # Idempotent: second call also 204.
    resp2 = await client.post(
        f"/api/v1/notifications/{delivery_id}/read",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 204


# ---------------------------------------------------------------------------
# 7: POST /{id}/read -> 404, wrong user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_read_wrong_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /{id}/read -> 404 when delivery belongs to another user."""
    _, _, notif_id = await _create_sent_delivery(
        client, db_session, "owner1"
    )
    _, other_token = await _create_investor(client, "other1")

    # Get delivery ID (belongs to owner1).
    stmt = select(NotificationDelivery).where(
        NotificationDelivery.notification_id == notif_id,
    )
    result = await db_session.execute(stmt)
    delivery = result.scalars().first()
    assert delivery is not None

    # Other user tries to mark it.
    resp = await client.post(
        f"/api/v1/notifications/{delivery.id}/read",
        headers=auth_headers(other_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 8: POST /read-all -> 200, marks all, returns count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_all(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /read-all -> 200, marks all unread as read."""
    user_id, token = await _create_investor(client, "readall1")

    # Create two notifications -> two deliveries.
    for i in range(2):
        notif = await create_notification(
            db_session,
            type=NotificationType.SYSTEM,
            title=f"Test: readall_{i}",
            body=f"Body {i}",
            target_type=TargetType.USER,
            target_value=f"user:{user_id}",
        )
        await db_session.commit()
        await resolve_notification(db_session, notif)
        await db_session.commit()
        await deliver_notification(db_session, notif)
        await db_session.commit()

    # Verify unread count >= 2.
    resp_count = await client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(token),
    )
    assert resp_count.json()["count"] >= 2

    # Mark all as read.
    resp = await client.post(
        "/api/v1/notifications/read-all",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["marked"] >= 2

    # Verify unread count is now 0.
    resp_count2 = await client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(token),
    )
    assert resp_count2.json()["count"] == 0

    # Idempotent: second call -> marked=0.
    resp2 = await client.post(
        "/api/v1/notifications/read-all",
        headers=auth_headers(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["marked"] == 0
