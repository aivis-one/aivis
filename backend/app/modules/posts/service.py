# =============================================================================
# CBSHOME Backend -- Posts Service (Sprint 9.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Business logic for posts, banner dismissals, and events.
#
# FUNCTIONS:
#   Posts:
#     create_post()     -- create platform or company post (staff only)
#     update_post()     -- partial update (PATCH)
#     delete_post()     -- soft delete (is_deleted=True)
#     list_posts()      -- public feed with optional dismiss info
#     get_post()        -- single post by ID
#     dismiss_post()    -- per-user banner dismissal (idempotent)
#
#   Events:
#     create_event()           -- create calendar event (staff only)
#     update_event()           -- partial update (PATCH)
#     delete_event()           -- soft delete (is_deleted=True)
#     list_events()            -- published events (paginated)
#     list_upcoming_events()   -- next 30 days (no pagination)
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

import json
from datetime import datetime, timedelta, UTC
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.posts.constants import OwnerType
from app.modules.posts.models import Event, Post, PostDismiss
from app.modules.posts.schemas import (
    CreateEventRequest,
    CreatePostRequest,
    EventResponse,
    PostResponse,
    UpdateEventRequest,
    UpdatePostRequest,
)

logger = structlog.get_logger()

_VALID_OWNER_TYPES = frozenset(e.value for e in OwnerType)


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


async def create_post(
    session: AsyncSession,
    staff_id: UUID,
    body: CreatePostRequest,
) -> Post:
    """Create a new post (platform or company).

    Validates owner_type and owner_id consistency:
      - platform -> owner_id must be None
      - company  -> owner_id must reference an existing CompanyProfile

    Sets published_at when is_published=True.

    Args:
        session: Active DB session (caller commits).
        staff_id: Staff user creating the post.
        body: Validated request body.

    Returns:
        The created Post (flushed, not committed).

    Raises:
        BadRequestError: Invalid owner_type or missing/invalid owner_id.
    """
    if body.owner_type not in _VALID_OWNER_TYPES:
        raise BadRequestError(
            f"Invalid owner_type: {body.owner_type}. "
            f"Valid: {', '.join(sorted(_VALID_OWNER_TYPES))}"
        )

    if body.owner_type == OwnerType.PLATFORM and body.owner_id is not None:
        raise BadRequestError(
            "owner_id must be null for platform posts"
        )

    if body.owner_type == OwnerType.COMPANY:
        if body.owner_id is None:
            raise BadRequestError(
                "owner_id is required for company posts"
            )
        # Verify company exists.
        stmt = select(func.count()).where(CompanyProfile.id == body.owner_id)
        count = (await session.execute(stmt)).scalar_one()
        if count == 0:
            raise NotFoundError("Company not found")

    published_at = datetime.now(UTC) if body.is_published else None

    post = Post(
        owner_type=body.owner_type,
        owner_id=body.owner_id,
        title=body.title,
        body=body.body,
        cover_url=body.cover_url,
        tags=body.tags,
        is_banner=body.is_banner,
        is_published=body.is_published,
        published_at=published_at,
        created_by=staff_id,
    )
    session.add(post)
    await session.flush()

    await record_audit(
        session=session,
        event="post.created",
        actor_id=staff_id,
        actor_type="staff",
        target_type="post",
        target_id=post.id,
        data={"owner_type": body.owner_type, "title": body.title},
    )

    logger.info(
        "post_created",
        post_id=str(post.id),
        owner_type=body.owner_type,
        staff_id=str(staff_id),
    )

    return post


async def update_post(
    session: AsyncSession,
    post_id: UUID,
    body: UpdatePostRequest,
    staff_id: UUID,
) -> Post:
    """Partial update of a post (PATCH).

    Sets published_at when transitioning is_published to True.

    Args:
        session: Active DB session (caller commits).
        post_id: Post UUID.
        body: Validated request body (partial).
        staff_id: Staff user performing the update.

    Returns:
        Updated Post.

    Raises:
        NotFoundError: Post not found or soft-deleted.
    """
    post = await _get_post_or_404(session, post_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return post

    # Track publish transition.
    if "is_published" in updates and updates["is_published"] and not post.is_published:
        post.published_at = datetime.now(UTC)

    for field, value in updates.items():
        if field == "tags":
            post.set_jsonb("tags", value)
        else:
            setattr(post, field, value)

    await session.flush()

    await record_audit(
        session=session,
        event="post.updated",
        actor_id=staff_id,
        actor_type="staff",
        target_type="post",
        target_id=post.id,
        data={"fields": list(updates.keys())},
    )

    return post


async def delete_post(
    session: AsyncSession,
    post_id: UUID,
    staff_id: UUID,
) -> None:
    """Soft-delete a post (is_deleted=True).

    Args:
        session: Active DB session (caller commits).
        post_id: Post UUID.
        staff_id: Staff user performing the deletion.

    Raises:
        NotFoundError: Post not found or already deleted.
    """
    post = await _get_post_or_404(session, post_id)
    post.is_deleted = True
    await session.flush()

    await record_audit(
        session=session,
        event="post.deleted",
        actor_id=staff_id,
        actor_type="staff",
        target_type="post",
        target_id=post.id,
    )

    logger.info("post_deleted", post_id=str(post_id), staff_id=str(staff_id))


async def list_posts(
    session: AsyncSession,
    *,
    user_id: UUID | None = None,
    page: int = 1,
    per_page: int = 20,
    owner_type: str | None = None,
    company_id: UUID | None = None,
    tag: str | None = None,
) -> tuple[list[PostResponse], int]:
    """List published, non-deleted posts with optional dismiss info.

    If user_id is provided, LEFT JOIN PostDismiss to set is_dismissed.
    Otherwise is_dismissed is always False.

    Args:
        session: Active DB session (read-only).
        user_id: Authenticated user ID (None for anonymous).
        page: Page number (1-based).
        per_page: Items per page.
        owner_type: Filter by owner_type (exact match).
        company_id: Filter by owner_id (company posts only).
        tag: Filter by tag (JSONB array contains).

    Returns:
        (items, total) tuple.
    """
    conditions = [
        Post.is_published.is_(True),
        Post.is_deleted.is_(False),
    ]

    if owner_type:
        conditions.append(Post.owner_type == owner_type)
    if company_id:
        conditions.append(Post.owner_id == company_id)
    if tag:
        # JSONB @> operator: tags contains ["tag_value"].
        conditions.append(Post.tags.op("@>")(json.dumps([tag])))

    # Count total.
    count_stmt = (
        select(func.count())
        .select_from(Post)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page

    if user_id:
        # LEFT JOIN to check dismissed status per user.
        stmt = (
            select(Post, PostDismiss.id.label("dismiss_id"))
            .outerjoin(
                PostDismiss,
                (PostDismiss.post_id == Post.id)
                & (PostDismiss.user_id == user_id),
            )
            .where(*conditions)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(stmt)
        rows = result.all()

        items = []
        for post, dismiss_id in rows:
            resp = PostResponse.model_validate(post)
            resp.is_dismissed = dismiss_id is not None
            items.append(resp)
    else:
        # Anonymous: no dismiss check.
        stmt = (
            select(Post)
            .where(*conditions)
            .order_by(Post.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await session.execute(stmt)
        items = [
            PostResponse.model_validate(p) for p in result.scalars().all()
        ]

    return items, total


async def get_post(
    session: AsyncSession,
    post_id: UUID,
    user_id: UUID | None = None,
) -> PostResponse:
    """Get a single published post by ID.

    Args:
        session: Active DB session (read-only).
        post_id: Post UUID.
        user_id: Authenticated user ID (None for anonymous).

    Returns:
        PostResponse with is_dismissed populated.

    Raises:
        NotFoundError: Post not found, deleted, or not published.
    """
    conditions = [
        Post.id == post_id,
        Post.is_published.is_(True),
        Post.is_deleted.is_(False),
    ]

    if user_id:
        stmt = (
            select(Post, PostDismiss.id.label("dismiss_id"))
            .outerjoin(
                PostDismiss,
                (PostDismiss.post_id == Post.id)
                & (PostDismiss.user_id == user_id),
            )
            .where(*conditions)
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise NotFoundError("Post not found")
        post, dismiss_id = row
        resp = PostResponse.model_validate(post)
        resp.is_dismissed = dismiss_id is not None
        return resp
    else:
        stmt = select(Post).where(*conditions)
        result = await session.execute(stmt)
        post = result.scalar_one_or_none()
        if post is None:
            raise NotFoundError("Post not found")
        return PostResponse.model_validate(post)


async def dismiss_post(
    session: AsyncSession,
    user_id: UUID,
    post_id: UUID,
) -> None:
    """Dismiss a post for the current user (idempotent).

    Creates a PostDismiss record. If already dismissed, does nothing.

    Args:
        session: Active DB session (caller commits).
        user_id: Authenticated user ID.
        post_id: Post UUID.

    Raises:
        NotFoundError: Post not found, deleted, or not published.
    """
    # Verify post exists and is visible.
    stmt = select(func.count()).where(
        Post.id == post_id,
        Post.is_published.is_(True),
        Post.is_deleted.is_(False),
    )
    count = (await session.execute(stmt)).scalar_one()
    if count == 0:
        raise NotFoundError("Post not found")

    # Idempotent: try INSERT, ignore UNIQUE violation.
    dismiss = PostDismiss(
        post_id=post_id,
        user_id=user_id,
    )
    session.add(dismiss)

    try:
        await session.flush()
    except IntegrityError:
        # Already dismissed -- rollback the failed flush, continue.
        await session.rollback()


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


async def create_event(
    session: AsyncSession,
    staff_id: UUID,
    body: CreateEventRequest,
) -> Event:
    """Create a new calendar event.

    Args:
        session: Active DB session (caller commits).
        staff_id: Staff user creating the event.
        body: Validated request body.

    Returns:
        The created Event (flushed, not committed).
    """
    event = Event(
        title=body.title,
        description=body.description,
        cover_url=body.cover_url,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        location=body.location,
        url=body.url,
        is_published=body.is_published,
        created_by=staff_id,
    )
    session.add(event)
    await session.flush()

    await record_audit(
        session=session,
        event="event.created",
        actor_id=staff_id,
        actor_type="staff",
        target_type="event",
        target_id=event.id,
        data={"title": body.title},
    )

    logger.info(
        "event_created",
        event_id=str(event.id),
        staff_id=str(staff_id),
    )

    return event


async def update_event(
    session: AsyncSession,
    event_id: UUID,
    body: UpdateEventRequest,
    staff_id: UUID,
) -> Event:
    """Partial update of an event (PATCH).

    Args:
        session: Active DB session (caller commits).
        event_id: Event UUID.
        body: Validated request body (partial).
        staff_id: Staff user performing the update.

    Returns:
        Updated Event.

    Raises:
        NotFoundError: Event not found or soft-deleted.
    """
    event = await _get_event_or_404(session, event_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return event

    for field, value in updates.items():
        setattr(event, field, value)

    await session.flush()

    await record_audit(
        session=session,
        event="event.updated",
        actor_id=staff_id,
        actor_type="staff",
        target_type="event",
        target_id=event.id,
        data={"fields": list(updates.keys())},
    )

    return event


async def delete_event(
    session: AsyncSession,
    event_id: UUID,
    staff_id: UUID,
) -> None:
    """Soft-delete an event (is_deleted=True).

    Args:
        session: Active DB session (caller commits).
        event_id: Event UUID.
        staff_id: Staff user performing the deletion.

    Raises:
        NotFoundError: Event not found or already deleted.
    """
    event = await _get_event_or_404(session, event_id)
    event.is_deleted = True
    await session.flush()

    await record_audit(
        session=session,
        event="event.deleted",
        actor_id=staff_id,
        actor_type="staff",
        target_type="event",
        target_id=event.id,
    )

    logger.info("event_deleted", event_id=str(event_id), staff_id=str(staff_id))


async def list_events(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Event], int]:
    """List published, non-deleted events (paginated).

    Returns:
        (events, total) tuple.
    """
    conditions = [
        Event.is_published.is_(True),
        Event.is_deleted.is_(False),
    ]

    count_stmt = (
        select(func.count())
        .select_from(Event)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(Event)
        .where(*conditions)
        .order_by(Event.starts_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def list_upcoming_events(
    session: AsyncSession,
) -> list[Event]:
    """List published events starting within the next 30 days.

    No pagination -- returns all upcoming events sorted by starts_at ASC.

    Returns:
        List of upcoming events.
    """
    now = datetime.now(UTC)
    cutoff = now + timedelta(days=30)

    stmt = (
        select(Event)
        .where(
            Event.is_published.is_(True),
            Event.is_deleted.is_(False),
            Event.starts_at >= now,
            Event.starts_at <= cutoff,
        )
        .order_by(Event.starts_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_post_or_404(
    session: AsyncSession,
    post_id: UUID,
) -> Post:
    """Load a non-deleted post or raise 404."""
    stmt = select(Post).where(
        Post.id == post_id,
        Post.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    post = result.scalar_one_or_none()
    if post is None:
        raise NotFoundError("Post not found")
    return post


async def _get_event_or_404(
    session: AsyncSession,
    event_id: UUID,
) -> Event:
    """Load a non-deleted event or raise 404."""
    stmt = select(Event).where(
        Event.id == event_id,
        Event.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    event = result.scalar_one_or_none()
    if event is None:
        raise NotFoundError("Event not found")
    return event
