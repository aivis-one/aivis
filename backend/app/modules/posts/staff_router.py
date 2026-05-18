# =============================================================================
# CBSHOME Backend -- Posts Staff Router (Sprint 9.1, iter 2.6c B4)
# =============================================================================
#
# ENDPOINTS:
#   GET    /api/v1/staff/posts          -- list (includes drafts, B4)
#   POST   /api/v1/staff/posts          -- create post
#   PATCH  /api/v1/staff/posts/{id}     -- update post
#   DELETE /api/v1/staff/posts/{id}     -- soft-delete post
#   GET    /api/v1/staff/events         -- list (includes drafts, B4)
#   POST   /api/v1/staff/events         -- create event
#   PATCH  /api/v1/staff/events/{id}    -- update event
#   DELETE /api/v1/staff/events/{id}    -- soft-delete event
#
# AUTH:
#   All endpoints require content_manage permission.
#
# iter 2.6c B4:
#   GET /staff/posts and GET /staff/events surface unpublished
#   (is_published=False) rows alongside published ones -- the public
#   /api/v1/posts and /api/v1/events filter both endpoints down to
#   published only. Soft-deleted rows (is_deleted=True) stay hidden
#   from staff too; recovery flows go through a separate endpoint
#   when/if added.
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
from app.modules.auth.dependencies import require_staff_permission
from app.modules.posts.constants import OwnerType
from app.modules.posts.schemas import (
    CreateEventRequest,
    CreatePostRequest,
    EventListResponse,
    EventResponse,
    PostListResponse,
    PostResponse,
    UpdateEventRequest,
    UpdatePostRequest,
)
from app.modules.posts.service import (
    create_event,
    create_post,
    delete_event,
    delete_post,
    staff_list_events,
    staff_list_posts,
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


@staff_posts_router.get(
    "",
    response_model=PostListResponse,
)
async def staff_list_posts_endpoint(
    owner_type: OwnerType | None = Query(default=None),
    owner_id: UUID | None = Query(default=None),
    is_published: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_reader),
) -> PostListResponse:
    """List all posts (drafts included) with optional filters.

    iter 2.6c B4. The public /api/v1/posts filters is_published=True;
    this endpoint does not, so staff can see and edit drafts. Soft-
    deleted posts stay hidden -- recovery is a separate flow.

    Filters:
      owner_type      -- platform / company. Bound to OwnerType StrEnum
                         (iter 2.6c followup OBS-33-01); unknown values
                         are rejected with 422 at the framework edge
                         rather than silently returning an empty list.
      owner_id        -- company_profiles.id; only meaningful for
                         owner_type=company rows.
      is_published    -- None = both; True / False = exact match.
      search          -- case-insensitive substring on title;
                         service escapes %, _, \\ so literals match.
    """
    rows, total = await staff_list_posts(
        session,
        owner_type=owner_type.value if owner_type is not None else None,
        owner_id=owner_id,
        is_published=is_published,
        search=search,
        page=page,
        per_page=per_page,
    )
    return PostListResponse(
        items=[PostResponse.model_validate(p) for p in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


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


@staff_events_router.get(
    "",
    response_model=EventListResponse,
)
async def staff_list_events_endpoint(
    is_published: bool | None = Query(default=None),
    upcoming: bool | None = Query(
        default=None,
        description=(
            "true -> only future events (sorted by starts_at ASC); "
            "false -> only past events (DESC); omit for both (DESC)."
        ),
    ),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    staff: User = Depends(require_staff_permission("content_manage")),
    session: AsyncSession = Depends(get_db_reader),
) -> EventListResponse:
    """List all events (drafts + past + future) with optional filters.

    iter 2.6c B4. Mirrors GET /staff/posts: drafts surface, soft-
    deleted rows stay hidden. The `upcoming` flag splits the list
    on now() at request time -- the service captures one wall-clock
    value and uses it for both the count and the page so a slow
    request can't straddle the boundary.

    Sort order:
      upcoming=true  -> starts_at ASC (next event at the top).
      upcoming=false -> starts_at DESC (most recent past at the top).
      upcoming=None  -> starts_at DESC (matches the public list).
    """
    rows, total = await staff_list_events(
        session,
        is_published=is_published,
        upcoming=upcoming,
        search=search,
        page=page,
        per_page=per_page,
    )
    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


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
