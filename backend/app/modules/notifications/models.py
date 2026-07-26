# =============================================================================
# AIVIS.ONE Backend -- Notification Models (Sprint 8.1, Sprint 8.3)
# =============================================================================
#
# TWO-LEVEL ARCHITECTURE:
#
# Notification:
#   Channel-agnostic event record. One row per event (e.g. "purchase
#   confirmed"). Contains targeting info (target_type + target_value)
#   that the resolver expands into concrete NotificationDelivery rows.
#
# NotificationDelivery:
#   One row per recipient per channel. Created by the resolver stage
#   of the notification pipeline. Tracks delivery attempts and status.
#
# PIPELINE:
#   resolve:  Notification -> N NotificationDelivery (by target)
#   deliver:  NotificationDelivery -> ChannelFormatter -> external service
#   rollup:   NotificationDelivery statuses -> Notification.status
#
# IMMUTABILITY:
#   Notification body/title are immutable after creation. Only status
#   and scheduled_at/expiry_at are updated by the pipeline.
#
# CASCADE:
#   NotificationDelivery.notification_id -> CASCADE delete.
#   NotificationDelivery.user_id -> CASCADE delete (user removed = deliveries removed).
#
# Sprint 8.3:
#   NotificationDelivery.read_at -- timestamp when user marked delivery as read.
#   NULL = unread, non-NULL = read. Used by REST endpoints for badge counter.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import UUIDMixin
from app.modules.notifications.constants import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationStatus,
    NotificationType,
    TargetType,
)


class Notification(UUIDMixin, Base):
    """Channel-agnostic notification -- one row per event."""

    __tablename__ = "notifications"

    type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(
        String(5000),
        nullable=False,
    )

    target_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    target_value: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    action_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        default=5,
        server_default="5",
        nullable=False,
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    expiry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} type={self.type} "
            f"status={self.status} target={self.target_type}:{self.target_value}>"
        )


class NotificationDelivery(UUIDMixin, Base):
    """Per-user, per-channel delivery record."""

    __tablename__ = "notification_deliveries"

    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    channel_options: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=DeliveryStatus.PENDING,
        server_default=DeliveryStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Sprint 8.3: read tracking for REST endpoints.
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationDelivery id={self.id} "
            f"channel={self.channel} status={self.status} "
            f"user={self.user_id}>"
        )
