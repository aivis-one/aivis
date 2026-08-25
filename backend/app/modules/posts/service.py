# =============================================================================
# AIVIS.ONE Backend -- Posts Service (Sprint 9.1, review fixes)
# =============================================================================
#
# RESPONSIBILITY:
#   Business logic for posts, banner dismissals, and events.
#
# FUNCTIONS:
#   Posts:
#     create_post()        -- create platform or company post (staff only)
#     update_post()        -- partial update (PATCH)
#     delete_post()        -- soft delete (is_deleted=True)
#     list_posts()         -- public feed with optional dismiss info
#     staff_list_posts()   -- staff feed: includes drafts (iter 2.6c B4)
#     get_post()           -- single post by ID
#     dismiss_post()       -- per-user banner dismissal (idempotent)
#
#   Events:
#     create_event()           -- create calendar event (staff only)
#     update_event()           -- partial update (PATCH)
#     delete_event()           -- soft delete (is_deleted=True)
#     list_events()            -- published events (paginated, ?upcoming)
#     list_upcoming_events()   -- next N (?limit, default 3, max 50)
#     staff_list_events()      -- staff feed: includes drafts +
#                                upcoming/past split (iter 2.6c B4)
#
# REVIEW FIXES:
#   - dismiss_post: begin_nested() SAVEPOINT instead of session.rollback()
#   - list_upcoming_events: limit clamped to
#                           settings.events_upcoming_max_limit (50);
#                           30-day window dropped in iter 2.7b (A1-i)
#   - owner_type validation moved to Pydantic Literal (schema layer)
#
# COMMIT RULE (P-01):
#   Service never commits. Caller manages the transaction.
# =============================================================================

import json
from datetime import datetime, UTC
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.posts.constants import OwnerType
from app.modules.posts.models import Event, Post, PostDismiss
from app.modules.posts.schemas import (
    CreateCompanyPostRequest,
    CreateEventRequest,
    CreatePostRequest,
    EventResponse,
    PostResponse,
    UpdateCompanyPostRequest,
    UpdateEventRequest,
    UpdatePostRequest,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------


async def create_post(
    session: AsyncSession,
    staff_id: UUID,
    body: CreatePostRequest,
) -> Post:
    """Create a new post (platform or company).

    Validates owner_id consistency:
      - platform -> owner_id must be None
      - company  -> owner_id must reference an existing CompanyProfile

    owner_type is validated by Pydantic Literal in schema.
    Sets published_at when is_published=True.

    Args:
        session: Active DB session (caller commits).
        staff_id: Staff user creating the post.
        body: Validated request body.

    Returns:
        The created Post (flushed, not committed).

    Raises:
        BadRequestError: Missing/invalid owner_id for owner_type.
        NotFoundError: Company not found for company posts.
    """
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
    await session.refresh(post)

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


# ---------------------------------------------------------------------------
# Company self-service posts (TASK-30)
# ---------------------------------------------------------------------------
#
# A company writing about itself. owner_type/owner_id are ALWAYS forced
# to "company" / the caller's own company_id here -- never taken from
# the request body -- so a project can never create, edit, or delete a
# post for a different owner_id. Mirrors create_post/update_post/
# delete_post's shape (same published_at transition logic, same soft
# delete), but is deliberately a separate code path rather than a thin
# wrapper around the staff functions: the staff functions always audit
# with target_type="post", and TASK-30's ruling on this feature is to
# audit with target_type="company" instead (see AUDIT DECISION below),
# so the record_audit() call itself has to differ, not just its
# arguments.
#
# AUDIT DECISION: target_type="company", target_id=company_id (NOT
# target_type="post"). audit/service.py's list_company_audit_feed()
# (GET /api/v1/staff/audit/companies, gated project_manage) filters
# strictly on target_type="company" -- an entry keyed to the post's own
# id would never surface there when an admin pulls up "everything this
# project wrote about itself" by company_id. A project's own news post
# is squarely inside that admin question, so it should show up in that
# feed; that requires keying to the company, matching the precedent
# audit/service.py's own module docstring sets for exactly this next
# step ("flagged for whoever builds the roadmap-editing / attachment-
# upload self-service write paths next ... decide whether to key those
# events to the sub-entity ... or to the company (so they show up
# here too)"). The post_id is still recorded inside `data` for
# traceability, so nothing is lost by not keying to it.
# ---------------------------------------------------------------------------


async def _get_company_post_or_404(
    session: AsyncSession,
    company_id: UUID,
    post_id: UUID,
) -> Post:
    """Load a non-deleted post owned by `company_id`, or raise 404.

    404 (not 403) on a post that exists but belongs to a different
    company, or to the platform -- same isolation contract as
    companies/attachments_router.py ("A 404 (not 403) on a hidden /
    deleted / cross-company attachment ... avoids confirming
    existence"). A company must not be able to learn that a given
    post ID exists and belongs to someone else.
    """
    stmt = select(Post).where(
        Post.id == post_id,
        Post.owner_type == OwnerType.COMPANY,
        Post.owner_id == company_id,
        Post.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    post = result.scalar_one_or_none()
    if post is None:
        raise NotFoundError("Post not found")
    return post


async def create_company_post(
    session: AsyncSession,
    company_id: UUID,
    actor_user_id: UUID,
    body: CreateCompanyPostRequest,
) -> Post:
    """Create a post owned by the caller's own company (TASK-30).

    owner_type/owner_id are forced to "company" / company_id here --
    never read from `body`, which has no such fields. is_banner is
    always False (see CreateCompanyPostRequest docstring).

    Args:
        session: Active DB session (caller commits).
        company_id: The caller's own company_profiles.id, resolved
            server-side from the auth token (never from the URL/body).
        actor_user_id: The company user's own users.id -- recorded as
            Post.created_by and as the audit actor_id.
        body: Validated request body (no owner_type/owner_id/is_banner).

    Returns:
        The created Post (flushed, not committed).
    """
    published_at = datetime.now(UTC) if body.is_published else None

    post = Post(
        owner_type=OwnerType.COMPANY,
        owner_id=company_id,
        title=body.title,
        body=body.body,
        cover_url=body.cover_url,
        tags=body.tags,
        is_banner=False,
        is_published=body.is_published,
        published_at=published_at,
        created_by=actor_user_id,
    )
    session.add(post)
    await session.flush()

    await record_audit(
        session=session,
        event="company.post_created",
        actor_id=actor_user_id,
        actor_type="user",
        target_type="company",
        target_id=company_id,
        data={"post_id": str(post.id), "title": body.title},
    )

    logger.info(
        "company_post_created",
        post_id=str(post.id),
        company_id=str(company_id),
        actor_user_id=str(actor_user_id),
    )

    return post


async def update_company_post(
    session: AsyncSession,
    company_id: UUID,
    post_id: UUID,
    actor_user_id: UUID,
    body: UpdateCompanyPostRequest,
) -> Post:
    """Partial update (PATCH) of a post owned by the caller's company.

    Args:
        session: Active DB session (caller commits).
        company_id: The caller's own company_profiles.id.
        post_id: Post UUID.
        actor_user_id: The company user's own users.id.
        body: Validated request body (partial; no owner_type/owner_id/
            is_banner -- those cannot be changed via this surface).

    Returns:
        Updated Post.

    Raises:
        NotFoundError: Post not found, deleted, or not owned by
            `company_id` (platform posts and other companies' posts
            both 404 here -- see _get_company_post_or_404).
    """
    post = await _get_company_post_or_404(session, company_id, post_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return post

    if "is_published" in updates and updates["is_published"] and not post.is_published:
        post.published_at = datetime.now(UTC)

    for field, value in updates.items():
        if field == "tags":
            post.set_jsonb("tags", value)
        else:
            setattr(post, field, value)

    await session.flush()
    await session.refresh(post)

    await record_audit(
        session=session,
        event="company.post_updated",
        actor_id=actor_user_id,
        actor_type="user",
        target_type="company",
        target_id=company_id,
        data={"post_id": str(post.id), "fields": list(updates.keys())},
    )

    return post


async def delete_company_post(
    session: AsyncSession,
    company_id: UUID,
    post_id: UUID,
    actor_user_id: UUID,
) -> None:
    """Soft-delete (is_deleted=True) a post owned by the caller's company.

    Args:
        session: Active DB session (caller commits).
        company_id: The caller's own company_profiles.id.
        post_id: Post UUID.
        actor_user_id: The company user's own users.id.

    Raises:
        NotFoundError: Post not found, deleted, or not owned by
            `company_id`.
    """
    post = await _get_company_post_or_404(session, company_id, post_id)
    post.is_deleted = True
    await session.flush()

    await record_audit(
        session=session,
        event="company.post_deleted",
        actor_id=actor_user_id,
        actor_type="user",
        target_type="company",
        target_id=company_id,
        data={"post_id": str(post.id)},
    )

    logger.info(
        "company_post_deleted",
        post_id=str(post_id),
        company_id=str(company_id),
        actor_user_id=str(actor_user_id),
    )


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


async def staff_list_posts(
    session: AsyncSession,
    *,
    owner_type: str | None = None,
    owner_id: UUID | None = None,
    is_published: bool | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Post], int]:
    """Staff-side post list (iter 2.6c B4).

    Differs from list_posts() in two important ways:
      1. Does NOT filter on is_published -- staff need to see drafts.
         When the caller passes is_published explicitly (True / False)
         the filter is applied; otherwise drafts AND published rows
         flow through.
      2. Returns Post ORM rows, not PostResponse. The staff router
         validates into PostResponse with the default is_dismissed=False;
         staff have no per-user dismiss view on this surface.

    Always filters is_deleted=False -- soft-deleted posts stay hidden
    even from staff (recovery flows go through a future dedicated
    endpoint, not this list).

    Search is a case-insensitive substring match on title. LIKE
    metacharacters in the needle are escaped so a query like "50%"
    matches the literal "50%" rather than acting as a wildcard --
    mirrors the pattern in companies.service.list_companies (iter
    2.6c B2).

    Args:
        session: Read-only session is sufficient.
        owner_type: Filter by owner_type (platform / company).
        owner_id: Filter by owner_id (company_profiles.id). For
            platform posts owner_id is NULL on every row -- pass
            owner_type=platform on its own to see them.
        is_published: None = no filter; True / False = exact match.
        search: Case-insensitive substring match on Post.title.
        page, per_page: Pagination (1-based page).

    Returns:
        (rows, total) tuple. Newest first by created_at.
    """
    conditions = [Post.is_deleted.is_(False)]

    if owner_type is not None:
        conditions.append(Post.owner_type == owner_type)
    if owner_id is not None:
        conditions.append(Post.owner_id == owner_id)
    if is_published is not None:
        conditions.append(Post.is_published.is_(is_published))
    if search is not None:
        needle = search.strip()
        if needle:
            # Escape backslash first, then % and _ -- otherwise we
            # would double-escape the backslashes we are about to add.
            escaped = (
                needle.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append(
                Post.title.ilike(f"%{escaped}%", escape="\\")
            )

    # Count total.
    count_stmt = (
        select(func.count())
        .select_from(Post)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(Post)
        .where(*conditions)
        .order_by(Post.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    return rows, total


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
    Uses SAVEPOINT (begin_nested) so IntegrityError doesn't roll back
    the outer transaction.

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

    # Idempotent: SAVEPOINT + INSERT, ignore UNIQUE violation.
    dismiss = PostDismiss(
        post_id=post_id,
        user_id=user_id,
    )
    try:
        async with session.begin_nested():
            session.add(dismiss)
            await session.flush()
    except IntegrityError:
        # Already dismissed -- SAVEPOINT rolled back, outer txn intact.
        pass


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
    await session.refresh(event)

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
    upcoming: bool | None = None,
) -> tuple[list[Event], int]:
    """List published, non-deleted events (paginated).

    iter 2.7b A: optional `upcoming` time-window split, mirroring
    staff_list_events so the public list and the staff list behave
    identically on the now() boundary:
        upcoming=True  -> Event.starts_at >= now(), ORDER BY ASC.
        upcoming=False -> Event.starts_at <  now(), ORDER BY DESC.
        upcoming=None  -> no time filter, ORDER BY DESC.
    upcoming=None reproduces the pre-2.7b behaviour exactly (DESC,
    full pagination) so existing callers and tests are unaffected.

    Returns:
        (events, total) tuple. Order depends on `upcoming` -- see above.
    """
    conditions = [
        Event.is_published.is_(True),
        Event.is_deleted.is_(False),
    ]

    # Time-window split. Captured once so the count and the page select
    # agree on the wall clock; otherwise a slow query could straddle the
    # boundary and the page returns rows the count missed. Same pattern
    # as staff_list_events.
    if upcoming is not None:
        now = datetime.now(UTC)
        if upcoming:
            conditions.append(Event.starts_at >= now)
        else:
            conditions.append(Event.starts_at < now)

    count_stmt = (
        select(func.count())
        .select_from(Event)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # ASC for upcoming=True so the next event surfaces first; DESC for
    # everything else (past split, or the unfiltered default).
    order_clause = (
        Event.starts_at.asc()
        if upcoming is True
        else Event.starts_at.desc()
    )

    stmt = (
        select(Event)
        .where(*conditions)
        .order_by(order_clause)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return items, total


async def list_upcoming_events(
    session: AsyncSession,
    *,
    limit: int = 3,
) -> list[Event]:
    """List published events starting now or later, soonest first.

    iter 2.7b A (A1-i): the previous 30-day upper window was dropped.
    "Upcoming" now means simply starts_at >= now() with no far-future
    cap -- the dashboard widget wants the next N events whenever they
    are, not only those inside an arbitrary month. The only bound is
    `limit`.

    `limit` is clamped to settings.events_upcoming_max_limit (50) here
    in the service rather than at the router so an over-large value
    degrades gracefully to the ceiling instead of failing the request
    with a 422 -- the caller asking for "too many" still gets a sensible
    page. The router supplies the default (3) and a floor (ge=1); the
    ceiling lives in config.

    Returns:
        Published, non-deleted events with starts_at >= now(), sorted
        ascending, capped at min(limit, 50).
    """
    now = datetime.now(UTC)
    effective_limit = min(limit, settings.events_upcoming_max_limit)

    stmt = (
        select(Event)
        .where(
            Event.is_published.is_(True),
            Event.is_deleted.is_(False),
            Event.starts_at >= now,
        )
        .order_by(Event.starts_at.asc())
        .limit(effective_limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def staff_list_events(
    session: AsyncSession,
    *,
    is_published: bool | None = None,
    upcoming: bool | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Event], int]:
    """Staff-side event list (iter 2.6c B4).

    Differs from list_events() in three important ways:
      1. Does NOT filter on is_published -- staff see drafts. When
         the caller passes is_published explicitly the filter is
         applied; otherwise drafts AND published rows flow through.
      2. Optional upcoming filter:
           upcoming=True  -> Event.starts_at >= now(), ORDER BY ASC.
           upcoming=False -> Event.starts_at <  now(), ORDER BY DESC.
           upcoming=None  -> no time filter, ORDER BY DESC.
         The ASC ordering for upcoming=True matches what a real
         calendar UI wants (the next event is at the top).
      3. Returns Event ORM rows, not validated responses.

    Always filters is_deleted=False.

    Search is a case-insensitive substring match on Event.title with
    LIKE metacharacters escaped (same pattern as staff_list_posts).

    Args:
        session: Read-only session is sufficient.
        is_published: None = no filter; True / False = exact match.
        upcoming: None = no time filter; True/False = split on now().
        search: Case-insensitive substring match on Event.title.
        page, per_page: Pagination (1-based page).

    Returns:
        (rows, total). Order depends on `upcoming` -- see above.
    """
    conditions = [Event.is_deleted.is_(False)]

    if is_published is not None:
        conditions.append(Event.is_published.is_(is_published))

    # Time-window split. Captured once so both the count and the page
    # select agree on the wall clock; otherwise a slow query could
    # straddle the boundary and the page returns rows the count missed.
    if upcoming is not None:
        now = datetime.now(UTC)
        if upcoming:
            conditions.append(Event.starts_at >= now)
        else:
            conditions.append(Event.starts_at < now)

    if search is not None:
        needle = search.strip()
        if needle:
            escaped = (
                needle.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append(
                Event.title.ilike(f"%{escaped}%", escape="\\")
            )

    # Count total.
    count_stmt = (
        select(func.count())
        .select_from(Event)
        .where(*conditions)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page. ASC ordering for upcoming=True so the next event
    # surfaces first; DESC for everything else so the most recently
    # scheduled / past event is at the top.
    order_clause = (
        Event.starts_at.asc()
        if upcoming is True
        else Event.starts_at.desc()
    )

    offset = (page - 1) * per_page
    stmt = (
        select(Event)
        .where(*conditions)
        .order_by(order_clause)
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    return rows, total


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
