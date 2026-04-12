# =============================================================================
# CBSHOME Backend -- Posts Public Router (Sprint 9.1)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/posts             -- post feed (paginated, filters)
#   GET  /api/v1/posts/{id}        -- single post
#   POST /api/v1/posts/{id}/dismiss -- dismiss banner
#   GET  /api/v1/events            -- event list (paginated)
#   GET  /api/v1/events/upcoming   -- next 30 days
#
# AUTH:
#   GET endpoints use get_optional_user (anonymous allowed).
#   POST /dismiss uses get_current_user_write (auth required).
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
from app.modules.auth.dependencies import get_current_user_write, get_optional_user
from app.modules.posts.schemas import (
    EventListResponse,
    EventResponse,
    PostListResponse,
    PostResponse,
)
from app.modules.posts.service import (
    dismiss_post,
    get_post,
    list_events,
    list_posts,
    list_upcoming_events,
)
from app.modules.users.models import User

logger = structlog.get_logger()

posts_router = APIRouter(prefix="/api/v1/posts", tags=["posts"])
events_router = APIRouter(prefix="/api/v1/events", tags=["events"])


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


@posts_router.get(
    "",
    response_model=PostListResponse,
)
async def list_posts_endpoint(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    owner_type: str | None = Query(default=None),
    company_id: UUID | None = Query(default=None),
    tag: str | None = Query(default=None),
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_reader),
) -> PostListResponse:
    """List published posts with optional filters.

    Anonymous access allowed. Authenticated users get is_dismissed info.
    """
    items, total = await list_posts(
        session,
        user_id=user.id if user else None,
        page=page,
        per_page=per_page,
        owner_type=owner_type,
        company_id=company_id,
        tag=tag,
    )
    return PostListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@posts_router.get(
    "/{post_id}",
    response_model=PostResponse,
)
async def get_post_endpoint(
    post_id: UUID,
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_reader),
) -> PostResponse:
    """Get a single published post by ID."""
    return await get_post(session, post_id, user_id=user.id if user else None)


@posts_router.post(
    "/{post_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def dismiss_post_endpoint(
    post_id: UUID,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Dismiss a post (hide banner). Auth required. Idempotent."""
    await dismiss_post(session, user.id, post_id)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@events_router.get(
    "",
    response_model=EventListResponse,
)
async def list_events_endpoint(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_reader),
) -> EventListResponse:
    """List published events (paginated)."""
    items, total = await list_events(session, page=page, per_page=per_page)
    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@events_router.get(
    "/upcoming",
    response_model=list[EventResponse],
)
async def upcoming_events_endpoint(
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_reader),
) -> list[EventResponse]:
    """List published events starting within the next 30 days."""
    events = await list_upcoming_events(session)
    return [EventResponse.model_validate(e) for e in events]
