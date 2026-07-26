# =============================================================================
# AIVIS.ONE Backend -- Notification Router (Sprint 8.3)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/notifications              -- list sent deliveries (paginated)
#   GET  /api/v1/notifications/unread-count  -- badge counter
#   POST /api/v1/notifications/{id}/read    -- mark delivery as read
#   POST /api/v1/notifications/read-all     -- mark all as read
#
# AUTH:
#   All endpoints require authenticated user.
#   GET endpoints use get_db_reader (read-only session).
#   POST endpoints use get_current_user_write + get_db_session (write session).
#
# DESIGN:
#   Frontend works with NotificationDelivery, not Notification directly.
#   Each delivery response is enriched with parent Notification data
#   (title, body, type, action_data, priority) via JOIN in service.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.notifications.schemas import (
    NotificationDeliveryResponse,
    NotificationListResponse,
    ReadAllResponse,
    UnreadCountResponse,
)
from app.modules.notifications.service import (
    get_unread_count,
    list_user_deliveries,
    mark_all_read,
    mark_delivery_read,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    type: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> NotificationListResponse:
    """List sent deliveries for the authenticated user.

    Only deliveries with status=sent are returned. Each delivery
    includes parent notification data (title, body, type, etc.).
    """
    items, total = await list_user_deliveries(
        session,
        user.id,
        page=page,
        per_page=per_page,
        type_filter=type,
        channel_filter=channel,
    )
    return NotificationListResponse(
        items=[NotificationDeliveryResponse(**item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
)
async def unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> UnreadCountResponse:
    """Get unread notification count for badge display."""
    count = await get_unread_count(session, user.id)
    return UnreadCountResponse(count=count)


@router.post(
    "/{delivery_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def read_notification(
    delivery_id: UUID,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Mark a single delivery as read.

    Idempotent: returns 204 whether delivery was already read or not.
    Returns 404 if delivery does not exist or belongs to another user.
    """
    await mark_delivery_read(session, user.id, delivery_id)


@router.post(
    "/read-all",
    response_model=ReadAllResponse,
)
async def read_all_notifications(
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> ReadAllResponse:
    """Mark all sent deliveries as read for the authenticated user.

    Returns the number of deliveries that were marked as read.
    """
    marked = await mark_all_read(session, user.id)
    return ReadAllResponse(marked=marked)
