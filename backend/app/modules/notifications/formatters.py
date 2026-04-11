# =============================================================================
# CBSHOME Backend -- Notification Formatters (Sprint 8.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Deliver a NotificationDelivery via its channel (telegram, email, etc.).
#
# ARCHITECTURE:
#   ChannelFormatter -- Protocol defining the deliver interface.
#   StubFormatter    -- Default implementation that always succeeds (logs only).
#
# SPRINT 8.2:
#   TelegramFormatter and EmailFormatter will be added here, each
#   implementing ChannelFormatter. Lazy init selects real vs stub based
#   on config (real token -> real formatter, TEST -> StubFormatter).
#
# FORMATTER REGISTRY:
#   get_formatter(channel) returns the appropriate formatter instance.
#   In Sprint 8.1 all channels use StubFormatter.
# =============================================================================

from typing import Protocol

import structlog

from app.modules.notifications.constants import DeliveryChannel
from app.modules.notifications.models import Notification, NotificationDelivery

logger = structlog.get_logger()


class ChannelFormatter(Protocol):
    """Protocol for channel-specific notification delivery."""

    async def deliver(
        self,
        notification: Notification,
        delivery: NotificationDelivery,
    ) -> bool:
        """Attempt to deliver a notification via this channel.

        Args:
            notification: The parent notification (title, body, action_data).
            delivery: The delivery record (user_id, channel, channel_options).

        Returns:
            True if delivery succeeded, False otherwise.
        """
        ...


class StubFormatter:
    """Stub formatter -- logs delivery and always succeeds.

    Used in Sprint 8.1 before real formatters are implemented.
    """

    async def deliver(
        self,
        notification: Notification,
        delivery: NotificationDelivery,
    ) -> bool:
        """Log the delivery attempt and return True."""
        logger.info(
            "stub_delivery",
            notification_id=str(notification.id),
            delivery_id=str(delivery.id),
            channel=delivery.channel,
            user_id=str(delivery.user_id),
            title=notification.title,
        )
        return True


# ---------------------------------------------------------------------------
# Formatter registry
# ---------------------------------------------------------------------------

_stub = StubFormatter()

_FORMATTERS: dict[str, ChannelFormatter] = {
    DeliveryChannel.TELEGRAM: _stub,
    DeliveryChannel.EMAIL: _stub,
    DeliveryChannel.PUSH: _stub,
    DeliveryChannel.IN_APP: _stub,
}


def get_formatter(channel: str) -> ChannelFormatter:
    """Get the formatter for a delivery channel.

    Falls back to StubFormatter for unknown channels.
    """
    return _FORMATTERS.get(channel, _stub)
