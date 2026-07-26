# =============================================================================
# AIVIS.ONE Backend -- Notification Schemas (Sprint 8.3)
# =============================================================================
#
# Pydantic models for notification REST endpoints.
#
# SCHEMAS:
#   NotificationDeliveryResponse -- single delivery with parent notification data
#   NotificationListResponse     -- paginated list of deliveries
#   UnreadCountResponse          -- badge counter
#   ReadAllResponse              -- result of mark-all-read operation
#
# DESIGN:
#   Frontend works with NotificationDelivery, not Notification directly.
#   Each delivery response is enriched with title, body, type, priority,
#   and action_data from the parent Notification (via JOIN in service).
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationDeliveryResponse(BaseModel):
    """Single delivery with parent notification data."""

    model_config = ConfigDict(from_attributes=True)

    # -- Delivery fields --
    id: UUID
    channel: str
    status: str
    read_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime

    # -- Parent notification fields (from JOIN) --
    type: str
    title: str
    body: str
    action_data: dict | None = None
    priority: int


class NotificationListResponse(BaseModel):
    """Paginated list of deliveries."""

    items: list[NotificationDeliveryResponse]
    total: int
    page: int
    per_page: int


class UnreadCountResponse(BaseModel):
    """Badge counter for unread deliveries."""

    count: int


class ReadAllResponse(BaseModel):
    """Result of mark-all-read operation."""

    marked: int
