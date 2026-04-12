# =============================================================================
# CBSHOME Backend -- Posts Staff Router (Sprint 9.1)
# =============================================================================
#
# ENDPOINTS:
#   POST   /api/v1/staff/posts          -- create post
#   PATCH  /api/v1/staff/posts/{id}     -- update post
#   DELETE /api/v1/staff/posts/{id}     -- soft-delete post
#   POST   /api/v1/staff/events         -- create event
#   PATCH  /api/v1/staff/events/{id}    -- update event
#   DELETE /api/v1/staff/events/{id}    -- soft-delete event
#
# AUTH:
#   All endpoints require content_manage permission.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import require_staff_permission
from app.modules.posts.schemas import (
    CreateEventRequest,
    CreatePostRequest,
    EventResponse,
    PostResponse,
    UpdateEventRequest,
    UpdatePostRequest,
)
from app.modules.posts.service import (
    create_event,
    create_post,
    delete_event,
    delete_post,
    update_event,
    update_post,
)
from app.modules.users.models import User

logger = structlog.get_logger()

staff_posts_router = APIRouter(
    prefix="/api/v1/staff/posts",
    tags=["staff-posts"],
)

staff_events_router = APIRouter(
    prefix="/api/v1/staff/events",
    tags=["staff-events"],
)


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


@staff_posts_router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def staff_create_post(
    body: CreatePostRequest,
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> PostResponse:
    """Create a platform or company post."""
    post = await create_post(session, staff.id, body)
    return PostResponse.model_validate(post)


@staff_posts_router.patch(
    "/{post_id}",
    response_model=PostResponse,
)
async def staff_update_post(
    post_id: UUID,
    body: UpdatePostRequest,
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> PostResponse:
    """Partial update of a post."""
    post = await update_post(session, post_id, body, staff.id)
    return PostResponse.model_validate(post)


@staff_posts_router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def staff_delete_post(
    post_id: UUID,
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete a post."""
    await delete_post(session, post_id, staff.id)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@staff_events_router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def staff_create_event(
    body: CreateEventRequest,
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> EventResponse:
    """Create a calendar event."""
    event = await create_event(session, staff.id, body)
    return EventResponse.model_validate(event)


@staff_events_router.patch(
    "/{event_id}",
    response_model=EventResponse,
)
async def staff_update_event(
    event_id: UUID,
    body: UpdateEventRequest,
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> EventResponse:
    """Partial update of an event."""
    event = await update_event(session, event_id, body, staff.id)
    return EventResponse.model_validate(event)


@staff_events_router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def staff_delete_event(
    event_id: UUID,
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete an event."""
    await delete_event(session, event_id, staff.id)
