# =============================================================================
# CBSHOME Backend -- Notification Constants (Sprint 8.1)
# =============================================================================
#
# Enums for the two-level notification architecture:
#   Notification  -- channel-agnostic event record
#   NotificationDelivery -- per-user, per-channel delivery record
#
# NOTIFICATION STATUS LIFECYCLE:
#   pending -> processing -> sent | partial_sent | failed | expired
#
# DELIVERY STATUS LIFECYCLE:
#   pending -> sent | failed
# =============================================================================

import enum


class NotificationStatus(enum.StrEnum):
    """Notification lifecycle status."""

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    PARTIAL_SENT = "partial_sent"
    FAILED = "failed"
    EXPIRED = "expired"


class DeliveryStatus(enum.StrEnum):
    """Per-user, per-channel delivery status."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class DeliveryChannel(enum.StrEnum):
    """Supported delivery channels."""

    TELEGRAM = "telegram"
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"


class NotificationType(enum.StrEnum):
    """Notification categories (indexed for filtering)."""

    SYSTEM = "system"
    TRANSACTION = "transaction"
    COMMISSION = "commission"
    NEWS = "news"
    INSTALLMENT = "installment"


class TargetType(enum.StrEnum):
    """How to resolve notification recipients."""

    USER = "user"
    ROLE = "role"
    ALL = "all"
