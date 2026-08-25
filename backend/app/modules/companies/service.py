# =============================================================================
# AIVIS.ONE Backend -- Company Service (Sprint 4.1 + Sprint F4.1 + F4.1.1 hotfix
#                                       + Sprint 4.3 + Refactor 2 iter 2.2 + 2.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_company()       -- create User (role=company) + CompanyProfile
#                             with total_supply / shares_per_option
#   assign_company()       -- TASK-30 ruling 1 + 9: promote an EXISTING
#                             user to company (no password ever passes
#                             through admin hands), full commercial
#                             terms required, no pool created here
#   update_company()       -- partial update profile/media/distribution_config
#                             (NO supply fields here -- see Sprint 4.3 note)
#   update_price()         -- change price + cascade to Products + history
#   get_company()          -- load CompanyProfile by id
#   list_companies()       -- paginated list (public: active only; staff: all;
#                             optional case-insensitive name search)
#   list_price_history()   -- paginated price-change records for a company
#                             (iter 2.6c B3, staff inspect/audit surface)
#   get_company_detail()   -- profile + roadmap items
#   create_roadmap_item()  -- add roadmap milestone
#   update_roadmap_item()  -- partial update roadmap item
#   delete_roadmap_item()  -- soft-delete (is_deleted=True)
#   reorder_roadmap()      -- bulk update order column
#
# Refactor 2 iter 2.2 ADDITIONS (Company Attachments):
#   create_attachment()           -- upload to MinIO + insert row + order shift
#   get_attachment()              -- load by id (scoped to company_id)
#   list_attachments()            -- filter by category / category_prefix /
#                                    language / publish flags / deleted
#   patch_attachment_metadata()   -- partial metadata update; shifts orders
#                                    when `order` is supplied
#   replace_attachment_file()     -- swap MinIO bytes; refresh storage_key,
#                                    mime_type, file_size_bytes, original_filename
#   soft_delete_attachment()      -- is_deleted=True; MinIO object preserved
#                                    so admins can restore via reconcile
#   hard_delete_attachment()      -- DELETE row + drop MinIO object
#   shift_orders_to_make_room()  -- bulk +1 on order inside (company_id,
#                                    category) to insert at target_order
#   reorder_attachments()         -- iter 2.6c B5: bulk reorder inside
#                                    one (company_id, category) scope
#
# Refactor 2 iter 2.3 ADDITIONS (Company Document Templates):
#   find_active_template()           -- 4-stage fallback lookup (R2 §4.7) in
#                                       a single SQL query, prioritised by
#                                       per-company-locale > per-company-en >
#                                       platform-locale > platform-en.
#   get_template_html_cached()       -- read <storage_prefix>/template.html
#                                       through a 5-min Redis cache
#                                       (R2 §4.10).
#   invalidate_template_html_cache() -- drop the Redis entry for one prefix
#                                       (called by reconcile scripts after
#                                       upload).
#   make_asset_data_uri_func()       -- pre-fetch every binary asset for one
#                                       template, return a sync callable
#                                       suitable for a Jinja2 global so the
#                                       renderer can stay sync (R2 §4.4).
#   get_template()                   -- load one template by id, scoped so
#                                       the caller's company_id matches OR
#                                       the row is a platform default
#                                       (company_id IS NULL).
#   list_templates()                 -- per-company rows + platform default
#                                       active rows for any (kind, language)
#                                       not covered by a per-company active.
#                                       Surfaces "what the renderer would
#                                       actually use" for staff inspection.
#
# Sprint F4.1 CHANGES:
#   - list_companies(): +search kwarg (case-insensitive ILIKE on name).
#     Used by the storefront filter bottom-sheet on the Investor side
#     to handle 500+ companies without shipping the whole catalogue.
#
# F4.1.1 hotfix:
#   - list_companies() escapes LIKE metacharacters ( % _ \ ) in the
#     search needle so a query like "50%" matches the literal string
#     "50%" in company names rather than being interpreted as "50*".
#   - WHERE construction uses sqlalchemy.and_(*conditions) instead of
#     a hand-rolled left-fold -- single line, no accidents when a
#     third filter is added.
#
# iter 2.6c B1:
#   - list_companies(): +status kwarg (exact-match on CompanyStatus).
#     Drives the staff list endpoint -- public router never passes
#     status, so the active_only=True path is unchanged. When status
#     IS supplied, it takes precedence over active_only.
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - create_company() persists total_supply and shares_per_option from
#     the request. Both required (NOT NULL on the column).
#   - update_company() intentionally does NOT support supply changes:
#       * total_supply changes go through pool admin endpoints
#         (PATCH /staff/companies/{id}/pool) so the pool / supply
#         relationship stays consistent.
#       * shares_per_option change is a split -- future scope, requires
#         pool migration and double-entry purchase migration.
#     UpdateCompanyRequest already excludes those fields, but the rule
#     is documented here for the next reader.
#   - Pool creation is NOT done here. Staff creates the company first,
#     then issues a pool via the pools endpoints (B2). This keeps the
#     two-step flow explicit and lets staff set equity_percent freely
#     instead of forcing a default of 100%.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# JSONB RULE:
#   distribution_config updated via set_jsonb(). Never direct assign.
#
# PRICE CASCADE:
#   When price changes, all active/hidden Products of this company
#   are updated and their installment templates soft-deleted.
#   Implemented via products/service.py cascade_price().
#
# STORAGE FAILURE MODEL (Refactor 2 iter 2.2):
#   create_attachment / replace_attachment_file upload to MinIO BEFORE
#   the DB write succeeds. If the DB transaction is later rolled back by
#   the caller, the MinIO object is left orphaned. This is intentional --
#   reconcile_attachments.py (E1, separate iteration step) sweeps both
#   directions: orphans (MinIO without a row) and broken records (row
#   with a missing object). For the hot path we accept the orphan over
#   a more complex two-phase commit.
# =============================================================================

import base64
import mimetypes
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import BinaryIO
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms_sync import ensure_recipient
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.redis import get_redis
from app.core.storage import (
    StorageError,
    delete_object,
    generate_presigned_url,
    get_object_bytes,
    upload_object,
)
from app.modules.auth.service import hash_password, get_platform_user_id
from app.modules.companies.constants import (
    ALLOWED_ATTACHMENT_MIME_TYPES,
    DocumentTemplateKind,
    ROADMAP_COVER_EXTENSION_TO_MIME,
    RoadmapItemKind,
    TEMPLATE_ASSET_EXTENSION_TO_MIME,
    TemplateStatus,
    VALID_COMPANY_STATUS_TRANSITIONS,
    validate_distribution_config,
)
from app.modules.companies.models import (
    CompanyAttachment,
    CompanyDocumentTemplate,
    CompanyPriceHistory,
    CompanyProfile,
    CompanyRoadmapItem,
    CompanyStatus,
    RoadmapItemStatus,
)
from app.modules.companies.schemas import (
    AssignCompanyRequest,
    AttachmentInboxMetadata,
    AttachmentPatchBody,
    CreateCompanyRequest,
    PostSnippetResponse,
    PublicCompanyStatsResponse,
    RoadmapItemResponse,
    UpdateCompanyRequest,
)
from app.modules.posts.models import Post
from app.modules.products.models import Product
from app.modules.users.models import KYCStatus, OnboardingStep, User, UserRole

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------


async def create_company(
    body: CreateCompanyRequest,
    staff: User,
    session: AsyncSession,
) -> CompanyProfile:
    """Create a new company: User (role=company) + CompanyProfile.

    Staff admin creates both the user account and the company profile.
    Credentials are passed to the company representative by admin.

    Sprint 4.3: total_supply and shares_per_option are persisted from the
    request. The OptionPool is created separately via the pool admin
    endpoint -- this service does not auto-create one.

    Raises:
        BadRequestError: If distribution_config is invalid.
        ConflictError: If email already exists.
    """
    # Validate distribution_config.
    validate_distribution_config(body.distribution_config)

    # Sprint 7.2: default referrer is Platform.
    platform_id = await get_platform_user_id(session)

    # Create User with role=company.
    password_hash = await hash_password(body.password)
    company_user = User(
        role=UserRole.COMPANY,
        is_active=True,
        onboarding_step=OnboardingStep.ROLE_SELECTED,
        kyc_status=KYCStatus.NOT_STARTED,
        referred_by=platform_id,
        credentials={
            "email": {
                "email": body.email.lower().strip(),
                "password_hash": password_hash,
            },
        },
        profile={},
        language="en",
    )
    session.add(company_user)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "ix_users_email" in str(exc.orig):
            raise ConflictError("Email already registered")
        raise

    # A company user is a recipient like any other -- comms must know
    # them before the first message (T-64). Never raises; a failure
    # defers the recipient to the outbox.
    await ensure_recipient(session, company_user)

    # Create CompanyProfile.
    profile = CompanyProfile(
        user_id=company_user.id,
        name=body.name,
        description=body.description,
        logo_url=body.logo_url,
        cover_url=body.cover_url,
        promo_video_url=body.promo_video_url,
        presentation_url=body.presentation_url,
        price_per_unit_cents=body.price_per_unit_cents,
        distribution_config=body.distribution_config,
        # Sprint 4.3: supply.
        total_supply=body.total_supply,
        shares_per_option=body.shares_per_option,
        status=CompanyStatus.HIDDEN,
    )
    session.add(profile)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_company_profiles_user_id" in str(exc.orig):
            raise ConflictError("Company profile already exists for this user")
        raise

    await session.refresh(profile)

    # Audit.
    await record_audit(
        session=session,
        event="company.created",
        actor_id=staff.id,
        actor_type="staff",
        target_type="company",
        target_id=profile.id,
        data={
            "name": body.name,
            "user_id": str(company_user.id),
            "total_supply": body.total_supply,
            "shares_per_option": body.shares_per_option,
        },
    )

    logger.info(
        "company_created",
        company_id=str(profile.id),
        user_id=str(company_user.id),
        staff_id=str(staff.id),
        total_supply=body.total_supply,
        shares_per_option=body.shares_per_option,
    )

    return profile


async def assign_company(
    body: AssignCompanyRequest,
    staff: User,
    session: AsyncSession,
) -> CompanyProfile:
    """Promote an EXISTING user to company, with full commercial terms.

    TASK-30 ruling 1 + revised ruling 9: mirrors staff/service.py's
    create_staff() -- the admin assigns an EXISTING user_id, never a
    password (ruling 1); the target's credentials are untouched by
    this call. Unlike create_staff (default permissions, nothing else
    to configure), a company assignment carries commercial terms, so
    AssignCompanyRequest requires every CreateCompanyRequest field
    except email/password.

    No OptionPool is created here, same as create_company: pool
    issuance stays a separate, later, explicit action via the pool
    admin endpoints (POST /staff/pools). A company with no pool yet is
    an existing, legal "fresh start-state" (see
    get_public_company_stats docstring above and
    PublicCompanyStatsResponse docstring in schemas.py).

    Raises:
        NotFoundError: If target user not found.
        BadRequestError: If distribution_config is invalid, or the
            target is the platform user.
        ConflictError: If the user already has a CompanyProfile (either
            role already COMPANY, or -- as a defence-in-depth race
            guard -- a concurrent assignment beat this one to the
            unique constraint on company_profiles.user_id).
    """
    # Validate distribution_config up front, same as create_company --
    # fail before touching the target user's role at all.
    validate_distribution_config(body.distribution_config)

    # Load target user.
    stmt = select(User).where(User.id == body.user_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        raise NotFoundError("User not found")

    if target.role == UserRole.PLATFORM:
        raise BadRequestError("Cannot assign platform user to a company")

    if target.role == UserRole.COMPANY:
        # Fast path -- avoids a doomed INSERT for the common case where
        # the caller retries an assignment they already made. The
        # IntegrityError catch below is the actual data-level guarantee
        # (race between two concurrent assign calls for the same user);
        # this check just gives the ordinary sequential case a cleaner,
        # earlier error before the profile insert is attempted.
        raise ConflictError("User is already a company")

    # Change role.
    target.role = UserRole.COMPANY

    # Create CompanyProfile.
    profile = CompanyProfile(
        user_id=target.id,
        name=body.name,
        description=body.description,
        logo_url=body.logo_url,
        cover_url=body.cover_url,
        promo_video_url=body.promo_video_url,
        presentation_url=body.presentation_url,
        price_per_unit_cents=body.price_per_unit_cents,
        distribution_config=body.distribution_config,
        total_supply=body.total_supply,
        shares_per_option=body.shares_per_option,
        status=CompanyStatus.HIDDEN,
    )
    session.add(profile)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_company_profiles_user_id" in str(exc.orig):
            raise ConflictError("Company profile already exists for this user")
        raise

    await session.refresh(profile)

    # A company user is a recipient like any other -- comms must know
    # them before the first message (T-64), same as create_company.
    # Never raises; a failure defers the recipient to the outbox.
    await ensure_recipient(session, target)

    # Audit.
    await record_audit(
        session=session,
        event="company.assigned",
        actor_id=staff.id,
        actor_type="staff",
        target_type="company",
        target_id=profile.id,
        data={
            "name": body.name,
            "user_id": str(target.id),
            "total_supply": body.total_supply,
            "shares_per_option": body.shares_per_option,
        },
    )

    logger.info(
        "company_assigned",
        company_id=str(profile.id),
        user_id=str(target.id),
        staff_id=str(staff.id),
        total_supply=body.total_supply,
        shares_per_option=body.shares_per_option,
    )

    return profile


async def update_company(
    company_id: UUID,
    body: UpdateCompanyRequest,
    staff: User,
    session: AsyncSession,
) -> CompanyProfile:
    """Partial update of company profile.

    If distribution_config is provided, it is re-validated.
    If status is provided, state machine transition is validated.

    Sprint 4.3 note: total_supply and shares_per_option are NOT updatable
    here. UpdateCompanyRequest does not expose them. See module docstring.

    Raises:
        NotFoundError: If company not found.
        BadRequestError: If distribution_config invalid or status transition invalid.
    """
    profile = await get_company(company_id, session)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return profile

    changed_fields = list(updates.keys())

    # -- Status transition --
    if "status" in updates:
        new_status = updates.pop("status")
        allowed = VALID_COMPANY_STATUS_TRANSITIONS.get(profile.status, frozenset())
        if new_status not in allowed:
            raise BadRequestError(
                f"Cannot transition from '{profile.status}' to '{new_status}'"
            )
        profile.status = new_status

    # -- distribution_config --
    if "distribution_config" in updates:
        new_config = updates.pop("distribution_config")
        validate_distribution_config(new_config)
        profile.set_jsonb("distribution_config", new_config)

    # -- Scalar fields --
    for field, value in updates.items():
        setattr(profile, field, value)

    await session.flush()
    await session.refresh(profile)

    # Audit.
    await record_audit(
        session=session,
        event="company.updated",
        actor_id=staff.id,
        actor_type="staff",
        target_type="company",
        target_id=profile.id,
        data={"fields": changed_fields},
    )

    logger.info(
        "company_updated",
        company_id=str(company_id),
        fields=changed_fields,
        staff_id=str(staff.id),
    )

    return profile


async def update_price(
    company_id: UUID,
    new_price: int,
    staff: User,
    session: AsyncSession,
) -> CompanyProfile:
    """Update company share price with cascade and history.

    1. Update CompanyProfile.price_per_unit_cents
    2. Cascade to active/hidden Products
    3. Insert CompanyPriceHistory record

    Raises:
        NotFoundError: If company not found.
        BadRequestError: If new price equals current price.
    """
    profile = await get_company(company_id, session)

    old_price = profile.price_per_unit_cents
    if old_price == new_price:
        raise BadRequestError("New price is the same as current price")

    # Update company price.
    profile.price_per_unit_cents = new_price

    # Cascade to Products: update price + soft-delete installment templates.
    from app.modules.products.service import cascade_price
    products_updated = await cascade_price(profile.id, new_price, session)

    # Record price history.
    history = CompanyPriceHistory(
        company_id=profile.id,
        price_per_unit_cents=new_price,
        changed_by=staff.id,
    )
    session.add(history)

    await session.flush()
    await session.refresh(profile)

    # Audit.
    await record_audit(
        session=session,
        event="company.price_updated",
        actor_id=staff.id,
        actor_type="staff",
        target_type="company",
        target_id=profile.id,
        data={"old_price": old_price, "new_price": new_price, "products_updated": products_updated},
    )

    logger.info(
        "company_price_updated",
        company_id=str(company_id),
        old_price=old_price,
        new_price=new_price,
        staff_id=str(staff.id),
    )

    return profile


async def get_company(
    company_id: UUID,
    session: AsyncSession,
) -> CompanyProfile:
    """Load CompanyProfile by id.

    Raises:
        NotFoundError: If company not found.
    """
    stmt = select(CompanyProfile).where(CompanyProfile.id == company_id)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()

    if profile is None:
        raise NotFoundError("Company not found")

    return profile


def _escape_like(needle: str) -> str:
    """Escape LIKE/ILIKE metacharacters so user input matches literally.

    The three metacharacters are: backslash (escape char itself), percent
    (any sequence), and underscore (any single char). Order matters --
    backslash MUST be escaped first, otherwise we would double-escape
    the backslashes we are about to add.
    """
    return (
        needle.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


async def list_companies(
    session: AsyncSession,
    *,
    active_only: bool = True,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[CompanyProfile], int]:
    """List companies with pagination.

    active_only=True for public endpoint (only active companies).
    active_only=False for staff endpoint (all companies).
    status: optional exact-match filter on CompanyProfile.status. When
            supplied it takes precedence over active_only -- the staff
            list endpoint passes active_only=False alongside an explicit
            status so the two never logically conflict, but documenting
            the precedence keeps a future caller from being surprised.
            Value range is validated to CompanyStatus at the router
            boundary; this layer trusts the incoming string.
    search: optional case-insensitive substring match on name. LIKE
            metacharacters in the needle are escaped so a user query
            like "50%" matches the literal "50%" rather than acting
            as a wildcard.

    Returns (companies, total_count).
    """
    conditions = []
    if status is not None:
        # Explicit status wins over active_only. Public router never
        # passes status, so this branch is the staff-list-only path.
        conditions.append(CompanyProfile.status == status)
    elif active_only:
        conditions.append(CompanyProfile.status == CompanyStatus.ACTIVE)
    if search is not None:
        needle = search.strip()
        if needle:
            escaped = _escape_like(needle)
            conditions.append(
                CompanyProfile.name.ilike(f"%{escaped}%", escape="\\")
            )

    where_clause = and_(*conditions) if conditions else True

    # Count total.
    count_stmt = select(func.count()).select_from(CompanyProfile).where(where_clause)
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(CompanyProfile)
        .where(where_clause)
        .order_by(CompanyProfile.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    companies = list(result.scalars().all())

    return companies, total


async def list_price_history(
    session: AsyncSession,
    company_id: UUID,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[CompanyPriceHistory], int]:
    """Paginated price-change records for one company (iter 2.6c B3).

    Sorted by changed_at DESC -- the most recent change is the one
    staff usually want to inspect or roll back. Mirrors the pagination
    contract used by list_companies so the wrapping
    PriceHistoryListResponse fits the same envelope shape as
    CompanyListResponse / every other staff list response.

    Args:
        session: read-only session is sufficient; we never write here.
        company_id: target company. Existence is verified up front so
            staff get a clean 404 from get_company rather than a
            confusing empty page when the UUID is wrong.

    Returns:
        (rows, total_count). `rows` may be empty for a freshly created
        company that has never had a price change.

    Raises:
        NotFoundError: company not found (propagated from get_company).
    """
    # Verify the company exists -- empty pagination on a non-existent
    # company would hide a bad request.
    await get_company(company_id, session)

    base_filter = CompanyPriceHistory.company_id == company_id

    # Count total.
    count_stmt = (
        select(func.count())
        .select_from(CompanyPriceHistory)
        .where(base_filter)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(CompanyPriceHistory)
        .where(base_filter)
        .order_by(CompanyPriceHistory.changed_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    return rows, total


async def get_company_detail(
    company_id: UUID,
    session: AsyncSession,
) -> tuple[CompanyProfile, list[CompanyRoadmapItem], dict[UUID, Post]]:
    """Load company profile with roadmap items and a map of referenced posts.

    R1 §5: roadmap items may reference Posts via `post_id`. We batch-
    load every Post referenced by any non-deleted item in a single
    SELECT so the response builder does not produce N+1 queries when
    embedding PostSnippetResponse.

    Only PUBLISHED, non-deleted posts make it into the map. Draft or
    soft-deleted posts behave as if the post_id were NULL at render
    time (the response simply omits the embedded snippet). This avoids
    leaking unpublished content via the roadmap surface.

    Excludes soft-deleted roadmap items.

    Raises:
        NotFoundError: If company not found.
    """
    profile = await get_company(company_id, session)

    stmt = (
        select(CompanyRoadmapItem)
        .where(
            CompanyRoadmapItem.company_id == company_id,
            CompanyRoadmapItem.is_deleted == False,  # noqa: E712
        )
        .order_by(CompanyRoadmapItem.order.asc())
    )
    result = await session.execute(stmt)
    roadmap_items = list(result.scalars().all())

    # Batch-load referenced posts (R1 §5). One SELECT for the whole
    # response, regardless of how many items reference a post.
    post_ids = [
        item.post_id for item in roadmap_items if item.post_id is not None
    ]
    posts_map: dict[UUID, Post] = {}
    if post_ids:
        posts_stmt = select(Post).where(
            Post.id.in_(post_ids),
            Post.is_deleted == False,  # noqa: E712
            Post.is_published == True,  # noqa: E712
        )
        posts_result = await session.execute(posts_stmt)
        posts_map = {p.id: p for p in posts_result.scalars().all()}

    return profile, roadmap_items, posts_map


def _post_excerpt(body: str, max_len: int = 200) -> str:
    """Plain-text excerpt of a Post body for embedded snippets (R1 §5).

    Post.body may contain Markdown or HTML; strip tags, collapse
    whitespace, truncate to max_len with an ellipsis. Pure-text input
    survives unchanged.
    """
    if not body:
        return ""
    stripped = re.sub(r"<[^>]+>", "", body)
    collapsed = re.sub(r"\s+", " ", stripped).strip()
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[:max_len].rstrip() + "..."


async def build_roadmap_item_response(
    item: CompanyRoadmapItem,
    post: Post | None,
    _session: AsyncSession,
) -> RoadmapItemResponse:
    """Render a CompanyRoadmapItem as RoadmapItemResponse (R1 §5).

    Generates a presigned URL for the cover image (when present) and
    embeds a PostSnippetResponse derived from the supplied Post.

    The Post argument is passed in by the caller (get_company_detail
    populates a posts_map, single-item callers do a one-row SELECT).
    This keeps the helper free of N+1 surprises.

    Storage failures on presign are logged and treated as "no cover"
    rather than failing the whole response: a missing object should
    not break the roadmap render for an unrelated reason.

    `_session` is kept in the signature with the underscore-prefix
    "intentionally unused" convention (same pattern as
    pools.service.with_consumed_remaining) so a future helper that
    needs DB access can be added without changing every call site.
    """
    cover_url: str | None = None
    if item.cover_storage_key:
        try:
            cover_url = await generate_presigned_url(item.cover_storage_key)
        except StorageError as exc:
            logger.warning(
                "roadmap_cover_presign_failed",
                item_id=str(item.id),
                storage_key=item.cover_storage_key,
                error=str(exc),
            )
            cover_url = None

    post_snippet: PostSnippetResponse | None = None
    if post is not None:
        post_snippet = PostSnippetResponse(
            id=post.id,
            title=post.title,
            cover_url=post.cover_url,
            excerpt=_post_excerpt(post.body),
        )

    return RoadmapItemResponse(
        id=item.id,
        kind=item.kind,
        title=item.title,
        description=item.description,
        target_date=item.target_date,
        valid_until=item.valid_until,
        status=item.status,
        order=item.order,
        external_url=item.external_url,
        post_id=item.post_id,
        linked_product_id=item.linked_product_id,
        cover_url=cover_url,
        post=post_snippet,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


# ---------------------------------------------------------------------------
# Public storefront stats (iter 2.4 R1 §1.6.2)
# ---------------------------------------------------------------------------


async def get_public_company_stats(
    company_id: UUID,
    session: AsyncSession,
) -> PublicCompanyStatsResponse:
    """Aggregate stats for the public company detail surface (R1 §1.6.2).

    Numbers:
      pool_total_options       -- size of the company's single active
                                  OptionPool. 0 if the company has no
                                  active pool (a fresh start-state
                                  company; rare but legal).
      options_sold             -- SUM(Purchase.units) for active
                                  purchases of the company. Reuses
                                  pools.service.get_pool_consumed which
                                  is the canonical "consumed" metric
                                  (includes sale, gift, installment
                                  tranche per spec §3.5-§3.7).
      options_sold_percent     -- int round of options_sold / total * 100.
                                  0 when total is 0.
      price_growth_90d_percent -- stretched-window growth (R1 §1.6.2
                                  decision):
                                    1. baseline = last CompanyPriceHistory
                                       row with changed_at < now-90d;
                                    2. if none, baseline = earliest
                                       CompanyPriceHistory row;
                                    3. if still none (history empty),
                                       growth = 0.
                                  Integer-rounded percent.

    Caller must have already 404'd hidden / archived companies; this
    helper assumes the company is valid and active.

    Lazy import of pools.service avoids the circular dependency
    (pools.service imports companies.service.get_company).
    """
    # Lazy import: pools.service.get_active_pool / get_pool_consumed both
    # need companies.service.get_company at module load, so a top-level
    # import here would loop.
    from app.modules.pools.service import (
        get_active_pool,
        get_pool_consumed,
    )

    # Pool sizing. A company without a pool returns zeros instead of a
    # 4xx: the storefront detail page must render even before Staff
    # has issued the pool, and a zero is a true statement.
    try:
        pool = await get_active_pool(company_id, session)
        pool_total_options = pool.total_options
    except BadRequestError:
        pool_total_options = 0

    options_sold = await get_pool_consumed(company_id, session)

    if pool_total_options > 0:
        options_sold_percent = int(
            round(options_sold / pool_total_options * 100)
        )
    else:
        options_sold_percent = 0

    # 90-day price growth, stretched-window semantics.
    growth_percent = 0
    profile = await get_company(company_id, session)
    current_price = profile.price_per_unit_cents

    cutoff = datetime.now(UTC) - timedelta(days=90)

    # Step 1: latest history row strictly older than 90 days. This is
    # the "true" baseline when the company has a long enough history.
    old_stmt = (
        select(CompanyPriceHistory.price_per_unit_cents)
        .where(
            CompanyPriceHistory.company_id == company_id,
            CompanyPriceHistory.changed_at < cutoff,
        )
        .order_by(CompanyPriceHistory.changed_at.desc())
        .limit(1)
    )
    old_price = (await session.execute(old_stmt)).scalar_one_or_none()

    if old_price is None:
        # Step 2 (stretched window): no row older than 90 days, fall
        # back to the earliest history row. Captures "the company has
        # been here for <90 days but has had a price change".
        earliest_stmt = (
            select(CompanyPriceHistory.price_per_unit_cents)
            .where(CompanyPriceHistory.company_id == company_id)
            .order_by(CompanyPriceHistory.changed_at.asc())
            .limit(1)
        )
        old_price = (
            await session.execute(earliest_stmt)
        ).scalar_one_or_none()

    # Step 3: no history rows at all (price never changed) -> 0%.
    # Also covers old_price == 0 which would zero-divide.
    if old_price and old_price > 0:
        growth_percent = int(
            round((current_price - old_price) / old_price * 100)
        )

    return PublicCompanyStatsResponse(
        pool_total_options=pool_total_options,
        options_sold=options_sold,
        options_sold_percent=options_sold_percent,
        price_growth_90d_percent=growth_percent,
    )


# ---------------------------------------------------------------------------
# Roadmap CRUD
# ---------------------------------------------------------------------------


async def create_roadmap_item(
    company_id: UUID,
    title: str,
    staff: User,
    session: AsyncSession,
    *,
    kind: str = RoadmapItemKind.MILESTONE.value,
    description: str | None = None,
    target_date=None,
    valid_until=None,
    status: str | None = None,
    external_url: str | None = None,
    post_id: UUID | None = None,
    linked_product_id: UUID | None = None,
) -> CompanyRoadmapItem:
    """Add a roadmap item to a company (R1 §5 extension).

    New items are placed at the end (max order + 1).

    Per-kind invariants (target_date / valid_until / status which-is-
    allowed-when) are enforced earlier by CreateRoadmapItemRequest's
    model_validator; this function trusts those constraints.

    Foreign-key invariants (linked_product_id belongs to this company,
    post_id refers to an existing non-deleted Post) are checked here
    because Pydantic does not see the DB.

    Raises:
        NotFoundError: company / post not found.
        BadRequestError: status invalid, or linked product belongs to
                         a different company.
    """
    # Verify company exists.
    await get_company(company_id, session)

    # Validate status if provided (legal value set independent of kind;
    # per-kind "is status allowed?" rule was applied by the schema).
    if status is not None:
        valid_statuses = {s.value for s in RoadmapItemStatus}
        if status not in valid_statuses:
            raise BadRequestError(
                f"Invalid roadmap item status: '{status}'. "
                f"Valid: {valid_statuses}"
            )

    # linked_product_id must point to a product belonging to THIS company.
    # Cross-company linking is rejected with 400 (not 404, because the
    # product exists -- it just shouldn't be referenced from here).
    if linked_product_id is not None:
        prod_stmt = select(Product).where(Product.id == linked_product_id)
        product = (await session.execute(prod_stmt)).scalar_one_or_none()
        if product is None:
            raise NotFoundError(
                f"Product {linked_product_id} not found"
            )
        if product.company_id != company_id:
            raise BadRequestError(
                f"linked_product_id {linked_product_id} belongs to a "
                f"different company"
            )

    # post_id must reference a Post that is not soft-deleted. Publication
    # status is intentionally NOT checked here -- a Staff member may
    # link a draft now and publish it later; render-time (get_company_detail)
    # filters out unpublished posts when assembling the response.
    if post_id is not None:
        post_stmt = select(Post.id).where(
            Post.id == post_id,
            Post.is_deleted == False,  # noqa: E712
        )
        post_exists = (await session.execute(post_stmt)).scalar_one_or_none()
        if post_exists is None:
            raise NotFoundError(f"Post {post_id} not found")

    # Determine next order value.
    max_order_stmt = (
        select(func.coalesce(func.max(CompanyRoadmapItem.order), -1))
        .where(
            CompanyRoadmapItem.company_id == company_id,
            CompanyRoadmapItem.is_deleted == False,  # noqa: E712
        )
    )
    max_order = (await session.execute(max_order_stmt)).scalar_one()

    item = CompanyRoadmapItem(
        company_id=company_id,
        kind=kind,
        title=title,
        description=description,
        target_date=target_date,
        valid_until=valid_until,
        status=status or RoadmapItemStatus.PLANNED,
        order=max_order + 1,
        external_url=external_url,
        post_id=post_id,
        linked_product_id=linked_product_id,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)

    # Audit.
    await record_audit(
        session=session,
        event="company.roadmap_item_created",
        actor_id=staff.id,
        actor_type="staff",
        target_type="roadmap_item",
        target_id=item.id,
        data={
            "company_id": str(company_id),
            "kind": kind,
            "title": title,
        },
    )

    return item


async def update_roadmap_item(
    company_id: UUID,
    item_id: UUID,
    staff: User,
    session: AsyncSession,
    *,
    title: str | None = None,
    description: str | None = ...,  # type: ignore[assignment]
    target_date=...,
    valid_until=...,
    status: str | None = None,
    external_url: str | None = ...,  # type: ignore[assignment]
    post_id: UUID | None = ...,  # type: ignore[assignment]
    linked_product_id: UUID | None = ...,  # type: ignore[assignment]
) -> CompanyRoadmapItem:
    """Partial update of a roadmap item (R1 §5 extension).

    Sentinel-pattern (`= ...`) on optional fields differentiates
    "not provided" (keep current value) from "explicit None"
    (clear the field). The caller (router) passes `...` when the
    field is absent from the PATCH body.

    State machine: roadmap items of kind=milestone are subject to the
    `completed -> *` forbidden rule -- once a milestone is completed,
    its status cannot be moved back. Events and announcements have no
    status-flow semantics, so this guard does not apply to them.

    `kind` is intentionally NOT updatable -- see UpdateRoadmapItemRequest
    docstring for rationale.

    Raises:
        NotFoundError: company / item / post not found.
        BadRequestError: status invalid, illegal status transition,
                         or linked product belongs to a different
                         company.
    """
    # Verify company exists.
    await get_company(company_id, session)

    item = await _get_roadmap_item(company_id, item_id, session)

    changed_fields: list[str] = []

    if title is not None:
        item.title = title
        changed_fields.append("title")

    if description is not ...:
        item.description = description
        changed_fields.append("description")

    if target_date is not ...:
        item.target_date = target_date
        changed_fields.append("target_date")

    if valid_until is not ...:
        item.valid_until = valid_until
        changed_fields.append("valid_until")

    if external_url is not ...:
        item.external_url = external_url
        changed_fields.append("external_url")

    # post_id change: validate existence before assignment.
    if post_id is not ...:
        if post_id is not None:
            post_stmt = select(Post.id).where(
                Post.id == post_id,
                Post.is_deleted == False,  # noqa: E712
            )
            post_exists = (
                await session.execute(post_stmt)
            ).scalar_one_or_none()
            if post_exists is None:
                raise NotFoundError(f"Post {post_id} not found")
        item.post_id = post_id
        changed_fields.append("post_id")

    # linked_product_id change: validate ownership.
    if linked_product_id is not ...:
        if linked_product_id is not None:
            prod_stmt = select(Product).where(
                Product.id == linked_product_id
            )
            product = (
                await session.execute(prod_stmt)
            ).scalar_one_or_none()
            if product is None:
                raise NotFoundError(
                    f"Product {linked_product_id} not found"
                )
            if product.company_id != company_id:
                raise BadRequestError(
                    f"linked_product_id {linked_product_id} belongs to "
                    f"a different company"
                )
        item.linked_product_id = linked_product_id
        changed_fields.append("linked_product_id")

    if status is not None:
        valid_statuses = {s.value for s in RoadmapItemStatus}
        if status not in valid_statuses:
            raise BadRequestError(
                f"Invalid roadmap item status: '{status}'. "
                f"Valid: {valid_statuses}"
            )
        # R1 §5 state machine: for kind=milestone, completed is terminal.
        # No-op self-transitions (completed -> completed) pass through
        # since the source status is unchanged.
        if (
            item.kind == RoadmapItemKind.MILESTONE.value
            and item.status == RoadmapItemStatus.COMPLETED.value
            and status != RoadmapItemStatus.COMPLETED.value
        ):
            raise BadRequestError(
                "Cannot move a completed milestone to another status. "
                "Soft-delete and recreate if the change is intentional."
            )
        item.status = status
        changed_fields.append("status")

    if changed_fields:
        await session.flush()
        await session.refresh(item)

        # Audit.
        await record_audit(
            session=session,
            event="company.roadmap_item_updated",
            actor_id=staff.id,
            actor_type="staff",
            target_type="roadmap_item",
            target_id=item.id,
            data={"company_id": str(company_id), "fields": changed_fields},
        )

    return item


async def delete_roadmap_item(
    company_id: UUID,
    item_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Soft-delete a roadmap item (is_deleted=True).

    Raises:
        NotFoundError: If company or item not found.
    """
    # Verify company exists.
    await get_company(company_id, session)

    item = await _get_roadmap_item(company_id, item_id, session)
    item.is_deleted = True
    await session.flush()

    # Audit.
    await record_audit(
        session=session,
        event="company.roadmap_item_deleted",
        actor_id=staff.id,
        actor_type="staff",
        target_type="roadmap_item",
        target_id=item.id,
        data={"company_id": str(company_id)},
    )


# ---------------------------------------------------------------------------
# Roadmap cover image (iter 2.4 R1 §5)
# ---------------------------------------------------------------------------


def validate_roadmap_cover_mime_by_filename(filename: str) -> tuple[str, str]:
    """Return (mime, extension) for a roadmap cover upload, or raise.

    Mirrors validate_attachment_mime_by_filename: trust the filename
    extension, NOT the client-supplied multipart Content-Type. A request
    claiming "image/png" while uploading evil.svg gets rejected here.

    Returns:
        Tuple (mime, ext-with-dot). Both lowercase. ext is preserved
        for use in the MinIO storage key.

    Raises:
        BadRequestError: extension absent or not in the whitelist.
    """
    lowered = filename.lower()
    # Manual split because os.path.splitext doesn't help for filenames
    # like "cover" (no extension) -- we want a clear 400 there too.
    dot = lowered.rfind(".")
    ext = lowered[dot:] if dot >= 0 else ""
    mime = ROADMAP_COVER_EXTENSION_TO_MIME.get(ext)
    if mime is None:
        allowed = sorted(ROADMAP_COVER_EXTENSION_TO_MIME.keys())
        raise BadRequestError(
            f"Unsupported cover image extension: '{ext}'. "
            f"Allowed: {allowed}"
        )
    return mime, ext


async def set_roadmap_cover(
    session: AsyncSession,
    company_id: UUID,
    item_id: UUID,
    staff: User,
    *,
    file_data: BinaryIO,
    file_size_bytes: int,
    content_type: str,
    file_extension: str,
) -> CompanyRoadmapItem:
    """Upload / replace the cover image of a roadmap item (R1 §5).

    Storage flow (same orphan-tolerant pattern as create_attachment):
      1. upload_object(new_key) BEFORE the DB write. If the outer
         transaction is later rolled back, the orphan stays in MinIO
         until a future reconcile-roadmap-covers sweep.
      2. session.flush() with the new cover_storage_key.
      3. AFTER flush, best-effort delete_object(old_key) when the new
         and old keys differ. Same-extension uploads overwrite in
         place and skip the delete. Failures here are logged, not
         raised -- a stale object is preferable to a 5xx response.

    Raises:
        NotFoundError: company / item not found.
        StorageError:  any MinIO failure on the upload step bubbles up
                       (the DB write has not happened yet, so this is
                       a clean rollback).
    """
    await get_company(company_id, session)
    item = await _get_roadmap_item(company_id, item_id, session)

    old_storage_key = item.cover_storage_key
    new_storage_key = (
        f"companies/{company_id}/roadmap/{item_id}/cover{file_extension}"
    )

    # Upload first. Orphan-on-rollback is acceptable here; a row
    # pointing at a missing object would not be.
    await upload_object(
        new_storage_key,
        file_data,
        content_type,
        content_length=file_size_bytes,
    )

    item.cover_storage_key = new_storage_key
    await session.flush()
    await session.refresh(item)

    # Same-extension replace overwrote the same MinIO key -- nothing
    # to clean up. Cross-extension replace leaves an old object that
    # we delete here, best-effort.
    if old_storage_key and old_storage_key != new_storage_key:
        try:
            await delete_object(old_storage_key)
        except StorageError as exc:
            logger.warning(
                "roadmap_cover_old_delete_failed",
                item_id=str(item_id),
                storage_key=old_storage_key,
                error=str(exc),
            )

    await record_audit(
        session=session,
        event="company.roadmap_cover_uploaded",
        actor_id=staff.id,
        actor_type="staff",
        target_type="roadmap_item",
        target_id=item.id,
        data={
            "company_id": str(company_id),
            "storage_key": new_storage_key,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
        },
    )

    logger.info(
        "roadmap_cover_uploaded",
        item_id=str(item.id),
        company_id=str(company_id),
        staff_id=str(staff.id),
        storage_key=new_storage_key,
        size=file_size_bytes,
    )

    return item


async def delete_roadmap_cover(
    company_id: UUID,
    item_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Remove the cover image from a roadmap item (R1 §5).

    Returns 404 when no cover is present -- the operation is explicit,
    not a silent no-op, so the Staff UI can decide what to render.

    Storage delete is best-effort: a missing object (manual deletion,
    eventual consistency window, etc.) does not block the DB update.

    Raises:
        NotFoundError: company / item not found, or item has no cover.
    """
    await get_company(company_id, session)
    item = await _get_roadmap_item(company_id, item_id, session)

    if item.cover_storage_key is None:
        raise NotFoundError("Roadmap item has no cover image")

    storage_key = item.cover_storage_key
    item.cover_storage_key = None
    await session.flush()

    try:
        await delete_object(storage_key)
    except StorageError as exc:
        logger.warning(
            "roadmap_cover_delete_failed",
            item_id=str(item_id),
            storage_key=storage_key,
            error=str(exc),
        )

    await record_audit(
        session=session,
        event="company.roadmap_cover_deleted",
        actor_id=staff.id,
        actor_type="staff",
        target_type="roadmap_item",
        target_id=item.id,
        data={
            "company_id": str(company_id),
            "storage_key": storage_key,
        },
    )


async def reorder_roadmap(
    company_id: UUID,
    item_ids: list[UUID],
    staff: User,
    session: AsyncSession,
) -> list[CompanyRoadmapItem]:
    """Reorder roadmap items by updating order column.

    item_ids must contain all non-deleted roadmap items for the company.

    Raises:
        NotFoundError: If company not found.
        BadRequestError: If item_ids don't match existing items.
    """
    # Verify company exists.
    await get_company(company_id, session)

    # Load all non-deleted items.
    stmt = (
        select(CompanyRoadmapItem)
        .where(
            CompanyRoadmapItem.company_id == company_id,
            CompanyRoadmapItem.is_deleted == False,  # noqa: E712
        )
    )
    result = await session.execute(stmt)
    items = {item.id: item for item in result.scalars().all()}

    # Validate: same set of IDs.
    provided_ids = set(item_ids)
    existing_ids = set(items.keys())

    if provided_ids != existing_ids:
        missing = existing_ids - provided_ids
        extra = provided_ids - existing_ids
        parts = []
        if missing:
            parts.append(f"missing: {[str(i) for i in missing]}")
        if extra:
            parts.append(f"unknown: {[str(i) for i in extra]}")
        raise BadRequestError(f"Reorder mismatch: {', '.join(parts)}")

    # Check for duplicates.
    if len(item_ids) != len(set(item_ids)):
        raise BadRequestError("Duplicate IDs in reorder list")

    # Apply new order.
    for new_order, item_id in enumerate(item_ids):
        items[item_id].order = new_order

    await session.flush()

    # Return items in new order.
    ordered = [items[item_id] for item_id in item_ids]
    for item in ordered:
        await session.refresh(item)

    # Audit.
    await record_audit(
        session=session,
        event="company.roadmap_reordered",
        actor_id=staff.id,
        actor_type="staff",
        target_type="company",
        target_id=company_id,
        data={"item_ids": [str(i) for i in item_ids]},
    )

    return ordered


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_roadmap_item(
    company_id: UUID,
    item_id: UUID,
    session: AsyncSession,
) -> CompanyRoadmapItem:
    """Load a non-deleted roadmap item by company and item ID.

    Raises:
        NotFoundError: If item not found or soft-deleted.
    """
    stmt = select(CompanyRoadmapItem).where(
        CompanyRoadmapItem.id == item_id,
        CompanyRoadmapItem.company_id == company_id,
        CompanyRoadmapItem.is_deleted == False,  # noqa: E712
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if item is None:
        raise NotFoundError("Roadmap item not found")

    return item


# ---------------------------------------------------------------------------
# Attachments (Refactor 2 iter 2.2)
# ---------------------------------------------------------------------------
#
# Object key naming follows R2 §2.2:
#     companies/<company_id>/attachments/<attachment_id>/<original_filename>
#
# Order semantics (Q-ATT-4): `order` is unique per (company_id, category)
# scope conceptually, but not enforced as a UNIQUE constraint in the DB --
# parallel inserts can briefly produce duplicates. Service callers that
# specify an explicit `order` go through shift_orders_to_make_room()
# which moves existing rows down by 1 to free the slot. New inserts with
# the schema's default order=0 land at the top of the category, pushing
# existing rows down. Reconcile-script inserts also go through this path.


_UNSAFE_STORAGE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]")
_MAX_STORAGE_FILENAME_LENGTH = 200


def _sanitize_storage_filename(filename: str) -> str:
    """Reduce an uploader-supplied filename to one safe MinIO key segment.

    Allow-list, not deny-list (TASK-6 4.2): keep ASCII letters, digits,
    spaces, dots, hyphens and underscores; drop everything else outright,
    including `/` and `\\`. Nothing in the allowed set can reconstruct a
    path separator, so the result has no ability to add or remove a path
    segment -- it is a label, never an instruction.

    Order matters: `../` becomes `..` once `/` is dropped, so dot runs
    are collapsed to one AFTER the character strip, not before -- doing
    it the other way would leave a bare `..` once the (by-then-illegal)
    slash around it disappears.

    Leading/trailing dots, spaces and hyphens are trimmed after that: a
    leading dot is a hidden file on POSIX, a leading hyphen reads as a
    flag to any tool that later touches these keys from a shell.

    A name that cleans to nothing -- all punctuation, a bare `..`, an
    empty string -- falls back to a fixed literal rather than an empty
    path segment, which would leave the key ending in `/`: directory-
    shaped, not file-shaped.
    """
    cleaned = _UNSAFE_STORAGE_FILENAME_CHARS.sub("", filename)
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = cleaned.strip(" .-")
    if not cleaned:
        return "untitled"
    return cleaned[:_MAX_STORAGE_FILENAME_LENGTH]


def build_storage_key(company_id: UUID, attachment_id: UUID, filename: str) -> str:
    """Build the canonical MinIO key for an attachment object.

    Mirrors the convention used by reconcile_attachments.py so direct DB
    inserts and inbox-driven inserts produce identical keys.

    Round 4 (QC-01): public name -- the reconcile script imports this
    helper directly and the underscore prefix would falsely signal an
    internal-only contract.

    TASK-6 4.2: `filename` is sanitised HERE, inside the shared helper,
    not at each call site -- the router and reconcile_attachments.py
    both call this function directly, and sanitising centrally is what
    keeps them producing identical keys for the same input instead of
    drifting the moment one call site's cleaning rule is edited and the
    other's is not. See _sanitize_storage_filename for the rule. This
    only changes what a NEW upload's key looks like; reads and deletes
    use the storage_key already stored on the row (unaffected -- see
    get_attachment / attachment.storage_key call sites), so no existing
    object is touched.
    """
    safe_filename = _sanitize_storage_filename(filename)
    return f"companies/{company_id}/attachments/{attachment_id}/{safe_filename}"


async def shift_orders_to_make_room(
    session: AsyncSession,
    company_id: UUID,
    category: str,
    target_order: int,
) -> None:
    """Bulk +1 on `order` for non-deleted attachments at `target_order`+ in
    the given (company_id, category) scope. Used to free a slot before
    inserting / repositioning an attachment.

    Soft-deleted rows are not shifted; they no longer have a meaningful
    position in the displayed list.

    Round 4 (QC-01): public name -- see build_storage_key above.
    """
    stmt = (
        update(CompanyAttachment)
        .where(
            CompanyAttachment.company_id == company_id,
            CompanyAttachment.category == category,
            CompanyAttachment.is_deleted == False,  # noqa: E712
            CompanyAttachment.order >= target_order,
        )
        .values(order=CompanyAttachment.order + 1)
    )
    await session.execute(stmt)


def validate_attachment_mime_by_filename(filename: str) -> str:
    """Resolve the MIME type from a filename's extension and enforce the
    attachment whitelist.

    Round 4 (SEC-01 / QC-02 / REF-01): unifies validation across the
    staff multipart router, the reconcile script, and any future
    consumer. The router used to trust `file.content_type` from the
    multipart header (client-controlled, trivial to spoof). Switching
    to extension-based detection means the filename is the source of
    truth -- the browser sets it from the OS extension mapping by
    default, and an explicitly-typed extension is what staff will type
    when uploading.

    Combined with `Content-Disposition: attachment` in the presigned
    URL (storage.generate_presigned_url), this closes the SVG-as-XSS
    vector: even if a bad actor wraps a malicious payload in a
    "trusted" extension, the browser downloads instead of rendering.

    Args:
        filename: Original filename from the upload (with extension).

    Returns:
        The validated MIME type from ALLOWED_ATTACHMENT_MIME_TYPES.

    Raises:
        BadRequestError: filename has no extension, or the extension
            does not map to a whitelisted MIME type.
    """
    if not filename:
        raise BadRequestError("Filename is required")
    # MINOR-03 (Round 11 review): normalise to lowercase so foo.PDF /
    # foo.Jpg behave identically to foo.pdf / foo.jpg. mimetypes can be
    # case-sensitive depending on the underlying mime.types DB, and the
    # roadmap-cover validator already does this -- keep both validators
    # consistent. Original filename is preserved for the error message.
    guess, _ = mimetypes.guess_type(filename.lower())
    if guess is None:
        raise BadRequestError(
            f"Cannot determine MIME type from filename: {filename!r}"
        )
    if guess not in ALLOWED_ATTACHMENT_MIME_TYPES:
        raise BadRequestError(f"Unsupported MIME type: {guess}")
    return guess


async def get_attachment(
    session: AsyncSession,
    company_id: UUID,
    attachment_id: UUID,
    *,
    include_deleted: bool = False,
) -> CompanyAttachment:
    """Load a single attachment scoped to its company.

    `company_id` is part of the lookup so a leaked attachment_id from one
    company can't be queried under another company's URL.

    Raises:
        NotFoundError: If the attachment doesn't exist, belongs to a
            different company, or is soft-deleted (when include_deleted=False).
    """
    conditions = [
        CompanyAttachment.id == attachment_id,
        CompanyAttachment.company_id == company_id,
    ]
    if not include_deleted:
        conditions.append(CompanyAttachment.is_deleted == False)  # noqa: E712

    stmt = select(CompanyAttachment).where(*conditions)
    result = await session.execute(stmt)
    attachment = result.scalar_one_or_none()

    if attachment is None:
        raise NotFoundError("Attachment not found")

    return attachment


async def list_attachments(
    session: AsyncSession,
    company_id: UUID,
    *,
    category: str | None = None,
    category_prefix: str | None = None,
    language: str | None = None,
    only_published: bool = False,
    only_public: bool = False,
    include_deleted: bool = False,
) -> list[CompanyAttachment]:
    """List attachments for a company with the requested filters applied.

    Auth-flow callers pass only_published=True, only_public ignored
        (auth users see public + private alike, as long as published).
    Public-flow callers pass only_published=True AND only_public=True.
    Staff-flow callers pass nothing (sees everything) or include_deleted
        when they want soft-deleted rows surfaced.

    `category` is exact match. `category_prefix` is LIKE prefix%, with
    metacharacters in the needle escaped so a literal '%' or '_' in the
    Staff-typed prefix matches itself. The two are mutually compatible
    -- if both are passed, both apply (caller's responsibility).

    Ordering is (category ASC, order ASC) so the Investor UI can build
    its L1 path-tree groups directly off the list.
    """
    conditions: list = [CompanyAttachment.company_id == company_id]

    if not include_deleted:
        conditions.append(CompanyAttachment.is_deleted == False)  # noqa: E712
    if only_published:
        conditions.append(CompanyAttachment.is_published == True)  # noqa: E712
    if only_public:
        conditions.append(CompanyAttachment.is_public == True)  # noqa: E712
    if category is not None:
        conditions.append(CompanyAttachment.category == category)
    if category_prefix is not None:
        # Pattern is treated as a literal prefix; only the trailing '%'
        # is a wildcard. _escape_like neutralises any metacharacter the
        # user typed inside the needle itself.
        escaped = _escape_like(category_prefix)
        conditions.append(
            CompanyAttachment.category.like(f"{escaped}%", escape="\\")
        )
    if language is not None:
        conditions.append(CompanyAttachment.language == language)

    stmt = (
        select(CompanyAttachment)
        .where(*conditions)
        .order_by(
            CompanyAttachment.category.asc(),
            CompanyAttachment.order.asc(),
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_attachment(
    session: AsyncSession,
    company_id: UUID,
    staff: User,
    *,
    file_data: bytes | BinaryIO,
    file_size_bytes: int,
    original_filename: str,
    content_type: str,
    metadata: AttachmentInboxMetadata,
) -> CompanyAttachment:
    """Create an attachment: upload bytes to MinIO, then insert the row.

    The attachment_id is generated up front so we can build storage_key
    deterministically (matches the reconcile-script convention). MinIO
    upload happens before the DB write -- if the outer transaction is
    rolled back later, the orphan is cleaned up by reconcile_attachments
    (R2 §3.7, broken-direction sweep).

    `metadata.order` is honoured: rows in the same (company_id, category)
    scope at order+ are shifted down by 1 to make room. The default
    order=0 from the schema means "land at the top of the category".

    Round 4 (PERF-01): `file_data` accepts bytes (legacy / reconcile
    path) or a binary stream (router multipart path). `file_size_bytes`
    is now an explicit caller-provided value because we cannot len() a
    stream -- the router gets it from `UploadFile.size` (set by
    Starlette from the multipart Content-Length), reconcile gets it
    from `len(downloaded_bytes)`.

    Raises:
        NotFoundError: If the company doesn't exist.
        StorageError: On any MinIO failure (bubbled up from upload_object).
    """
    await get_company(company_id, session)

    attachment_id = uuid4()
    storage_key = build_storage_key(company_id, attachment_id, original_filename)

    # Upload to MinIO first. A subsequent transaction rollback leaves an
    # orphan that reconcile_attachments will reap.
    await upload_object(
        storage_key, file_data, content_type, content_length=file_size_bytes
    )

    # Make room at the requested order inside (company_id, category).
    await shift_orders_to_make_room(
        session, company_id, metadata.category, metadata.order
    )

    attachment = CompanyAttachment(
        id=attachment_id,
        company_id=company_id,
        category=metadata.category,
        language=metadata.language,
        title=metadata.title,
        description=metadata.description,
        storage_key=storage_key,
        original_filename=original_filename,
        mime_type=content_type,
        file_size_bytes=file_size_bytes,
        order=metadata.order,
        is_published=metadata.is_published,
        is_public=metadata.is_public,
        created_by=staff.id,
    )
    session.add(attachment)
    await session.flush()
    await session.refresh(attachment)

    await record_audit(
        session=session,
        event="company.attachment_created",
        actor_id=staff.id,
        actor_type="staff",
        target_type="attachment",
        target_id=attachment.id,
        data={
            "company_id": str(company_id),
            "category": metadata.category,
            "language": metadata.language,
            "mime_type": content_type,
            "file_size_bytes": file_size_bytes,
            "is_published": metadata.is_published,
            "is_public": metadata.is_public,
        },
    )

    logger.info(
        "attachment_created",
        attachment_id=str(attachment.id),
        company_id=str(company_id),
        staff_id=str(staff.id),
        storage_key=storage_key,
        size=file_size_bytes,
    )

    return attachment


async def patch_attachment_metadata(
    session: AsyncSession,
    company_id: UUID,
    attachment_id: UUID,
    body: AttachmentPatchBody,
    staff: User,
) -> CompanyAttachment:
    """Partially update attachment metadata.

    The order column is rebalanced via shift_orders_to_make_room when
    a new `order` is supplied. The shift target category is the new
    category if it's part of the same patch, otherwise the existing one.

    Raises:
        NotFoundError: If the attachment doesn't exist.
    """
    attachment = await get_attachment(session, company_id, attachment_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return attachment

    changed_fields = list(updates.keys())

    new_category = updates.get("category", attachment.category)
    new_order = updates.get("order")

    if new_order is not None:
        # Free up a slot in the (possibly new) category before assigning.
        await shift_orders_to_make_room(
            session, company_id, new_category, new_order
        )

    for field, value in updates.items():
        setattr(attachment, field, value)

    await session.flush()
    await session.refresh(attachment)

    await record_audit(
        session=session,
        event="company.attachment_updated",
        actor_id=staff.id,
        actor_type="staff",
        target_type="attachment",
        target_id=attachment.id,
        data={"company_id": str(company_id), "fields": changed_fields},
    )

    logger.info(
        "attachment_updated",
        attachment_id=str(attachment.id),
        company_id=str(company_id),
        staff_id=str(staff.id),
        fields=changed_fields,
    )

    return attachment


async def replace_attachment_file(
    session: AsyncSession,
    company_id: UUID,
    attachment_id: UUID,
    staff: User,
    *,
    file_data: bytes | BinaryIO,
    file_size_bytes: int,
    original_filename: str,
    content_type: str,
) -> CompanyAttachment:
    """Swap the binary content of an existing attachment.

    Old MinIO object is deleted, the new one is uploaded under a fresh
    storage_key (the attachment_id stays, so the path prefix is stable
    but the trailing filename changes when `original_filename` changes).
    Metadata fields other than storage_key / mime_type / file_size_bytes
    / original_filename are untouched.

    Round 4 (PERF-01): see create_attachment for the file_data /
    file_size_bytes contract -- bytes for reconcile, BinaryIO for the
    multipart router path.

    Raises:
        NotFoundError: If the attachment doesn't exist.
        StorageError: On any MinIO failure.
    """
    attachment = await get_attachment(session, company_id, attachment_id)

    new_storage_key = build_storage_key(
        company_id, attachment.id, original_filename
    )
    old_storage_key = attachment.storage_key

    # Upload the new bytes first, then drop the old object. Done in this
    # order so a failed upload doesn't leave the row pointing nowhere.
    await upload_object(
        new_storage_key, file_data, content_type, content_length=file_size_bytes
    )
    if old_storage_key != new_storage_key:
        # delete_object is idempotent on a missing key, so a previous
        # partial replace that already removed the old object will not
        # error here.
        await delete_object(old_storage_key)

    attachment.storage_key = new_storage_key
    attachment.original_filename = original_filename
    attachment.mime_type = content_type
    attachment.file_size_bytes = file_size_bytes

    await session.flush()
    await session.refresh(attachment)

    await record_audit(
        session=session,
        event="company.attachment_replaced",
        actor_id=staff.id,
        actor_type="staff",
        target_type="attachment",
        target_id=attachment.id,
        data={
            "company_id": str(company_id),
            "old_storage_key": old_storage_key,
            "new_storage_key": new_storage_key,
            "mime_type": content_type,
            "file_size_bytes": file_size_bytes,
        },
    )

    logger.info(
        "attachment_replaced",
        attachment_id=str(attachment.id),
        company_id=str(company_id),
        staff_id=str(staff.id),
        old_storage_key=old_storage_key,
        new_storage_key=new_storage_key,
        size=file_size_bytes,
    )

    return attachment


async def soft_delete_attachment(
    session: AsyncSession,
    company_id: UUID,
    attachment_id: UUID,
    staff: User,
) -> None:
    """Mark the attachment as deleted (is_deleted=True). MinIO object
    stays so admins can restore via reconcile if needed.

    Raises:
        NotFoundError: If the attachment doesn't exist or is already
            soft-deleted.
    """
    attachment = await get_attachment(session, company_id, attachment_id)

    attachment.is_deleted = True
    await session.flush()

    await record_audit(
        session=session,
        event="company.attachment_soft_deleted",
        actor_id=staff.id,
        actor_type="staff",
        target_type="attachment",
        target_id=attachment.id,
        data={"company_id": str(company_id)},
    )

    logger.info(
        "attachment_soft_deleted",
        attachment_id=str(attachment.id),
        company_id=str(company_id),
        staff_id=str(staff.id),
    )


async def hard_delete_attachment(
    session: AsyncSession,
    company_id: UUID,
    attachment_id: UUID,
    staff: User,
) -> None:
    """Hard-delete: drop the row AND the MinIO object.

    Admin-only at the router layer (R2 §3.5, Q-ATT-1). Includes already
    soft-deleted rows so admins can finalise a deletion staff started.

    Raises:
        NotFoundError: If the attachment doesn't exist at all.
        StorageError: On any MinIO failure (re-raised after audit logging).
    """
    attachment = await get_attachment(
        session, company_id, attachment_id, include_deleted=True
    )

    storage_key = attachment.storage_key

    # Audit BEFORE the delete so we still have the row reference. If the
    # subsequent delete fails (DB or MinIO), the audit row is rolled back
    # alongside the rest of the transaction.
    await record_audit(
        session=session,
        event="company.attachment_hard_deleted",
        actor_id=staff.id,
        actor_type="staff",
        target_type="attachment",
        target_id=attachment.id,
        data={
            "company_id": str(company_id),
            "storage_key": storage_key,
            "was_soft_deleted": attachment.is_deleted,
        },
    )

    await session.delete(attachment)
    await session.flush()

    # MinIO drop happens after the row is gone. delete_object is
    # idempotent on a missing key, so a retried hard-delete of a row
    # whose object was already removed succeeds quietly.
    await delete_object(storage_key)

    logger.info(
        "attachment_hard_deleted",
        attachment_id=str(attachment_id),
        company_id=str(company_id),
        staff_id=str(staff.id),
        storage_key=storage_key,
    )


async def reorder_attachments(
    session: AsyncSession,
    company_id: UUID,
    category: str,
    item_ids: list[UUID],
    staff: User,
) -> None:
    """Bulk reorder attachments inside one (company_id, category) scope.

    iter 2.6c B5. Mirrors the contract of reorder_roadmap but scopes
    the operation to a single category -- attachment `order` is unique
    only per (company_id, category) (Q-ATT-4), so a per-company reorder
    would collapse the category-scoped invariant.

    Validation:
      * company exists (404 from get_company).
      * `item_ids` must be the exact set of non-deleted attachments
        currently in (company_id, category). Missing or extra ids
        produce a 400 with both diff sets in the message, mirroring
        reorder_roadmap so the Staff UI gets the same error shape.
      * No duplicates in `item_ids`.

    The category is regex-validated at the schema layer; this function
    trusts the incoming value.

    Soft-deleted attachments are excluded -- they have no meaningful
    position in the visible list, and including them in `item_ids`
    would surface as an "unknown id" 400 (correct behaviour: staff
    cannot reorder rows they cannot see).

    Args:
        session: Active write session (caller commits).
        company_id: Target company.
        category: Target category. Matched exactly against
            CompanyAttachment.category.
        item_ids: Complete ordered list of every non-deleted attachment
            id in the scope.
        staff: Acting staff user (audit log actor).

    Raises:
        NotFoundError: company not found.
        BadRequestError: set mismatch or duplicate ids.
    """
    # Verify company exists.
    await get_company(company_id, session)

    # Load all non-deleted attachments in (company_id, category).
    stmt = (
        select(CompanyAttachment)
        .where(
            CompanyAttachment.company_id == company_id,
            CompanyAttachment.category == category,
            CompanyAttachment.is_deleted == False,  # noqa: E712
        )
    )
    result = await session.execute(stmt)
    rows = {item.id: item for item in result.scalars().all()}

    # Validate: same set of ids.
    provided_ids = set(item_ids)
    existing_ids = set(rows.keys())

    if provided_ids != existing_ids:
        missing = existing_ids - provided_ids
        extra = provided_ids - existing_ids
        parts = []
        if missing:
            parts.append(f"missing: {[str(i) for i in missing]}")
        if extra:
            parts.append(f"unknown: {[str(i) for i in extra]}")
        raise BadRequestError(
            f"attachments_reorder_set_mismatch: {', '.join(parts)}"
        )

    # Check for duplicates.
    if len(item_ids) != len(set(item_ids)):
        raise BadRequestError(
            "attachments_reorder_set_mismatch: duplicate ids in payload"
        )

    # Apply new order in one transaction. Single flush at the end so
    # PostgreSQL never sees an intermediate state where two rows in
    # the scope share the same `order` value (UNIQUE on the scope is
    # not enforced at the DB level today, but the test contract still
    # expects atomicity).
    for new_order, item_id in enumerate(item_ids):
        rows[item_id].order = new_order

    await session.flush()

    # Audit.
    await record_audit(
        session=session,
        event="company.attachments_reordered",
        actor_id=staff.id,
        actor_type="staff",
        target_type="company",
        target_id=company_id,
        data={
            "category": category,
            "item_ids": [str(i) for i in item_ids],
        },
    )

    logger.info(
        "attachments_reordered",
        company_id=str(company_id),
        category=category,
        count=len(item_ids),
        staff_id=str(staff.id),
    )


# ---------------------------------------------------------------------------
# Document templates (Refactor 2 iter 2.3)
# ---------------------------------------------------------------------------
#
# Template metadata lives in `company_document_templates`; bytes (HTML +
# binary assets) live in MinIO under storage_prefix. R2 §4.
#
# 4-stage fallback (R2 §4.7):
#   1. company_id = X     AND language = user_lang AND status = active
#   2. company_id = X     AND language = 'en'      AND status = active
#   3. company_id IS NULL AND language = user_lang AND status = active
#   4. company_id IS NULL AND language = 'en'      AND status = active
# A miss is a 5xx -- platform defaults are guaranteed to be seeded.
#
# Redis cache (R2 §4.10):
#   key   ``template_html:<storage_prefix>``
#   value utf-8 decoded body of <storage_prefix>/template.html
#   TTL   5 minutes
#   Reconcile scripts call invalidate_template_html_cache() to drop the
#   entry on every replace; the next reader warms it again.


# Redis cache for the HTML body of templates. Key is the storage_prefix
# (which already encodes company_id / kind / language). 5-minute TTL is
# the upper bound on how stale a template render can be after staff
# uploads a new version through MinIO Web UI without running reconcile.
# Reconcile invalidates the entry explicitly, so the TTL only kicks in
# for unattended cluster nodes that miss the invalidation broadcast --
# which Redis handles centrally, so in practice the TTL is just a
# correctness backstop.
_TEMPLATE_HTML_CACHE_KEY_PREFIX: str = "template_html:"
_TEMPLATE_HTML_CACHE_TTL_SECONDS: int = 300


def _template_html_cache_key(storage_prefix: str) -> str:
    """Build the Redis key for the cached template.html body.

    Module-private helper so the prefix lives in exactly one place.
    """
    return f"{_TEMPLATE_HTML_CACHE_KEY_PREFIX}{storage_prefix}"


async def find_active_template(
    company_id: UUID,
    kind: DocumentTemplateKind | str,
    language: str,
    session: AsyncSession,
) -> CompanyDocumentTemplate | None:
    """Resolve the active template for (kind, language) using the 4-stage
    fallback (R2 §4.7).

    Single SQL query. The CASE-based ranking column is what enforces the
    stage order; ORDER BY priority + LIMIT 1 picks the winner. Stages 3-4
    are the platform default series (company_id IS NULL).

    Args:
        company_id: Caller's company. Stage 1-2 search rows owned by this
            company; stage 3-4 search the platform fallback (NULL).
        kind: DocumentTemplateKind value. Accepted as the StrEnum or as a
            bare string -- both compare equal to the column.
        language: Investor / staff locale. ISO 639-1.
        session: Async DB session (read-only here, no flush expected).

    Returns:
        The chosen CompanyDocumentTemplate row, or None if even the
        platform-default English fallback is missing -- which the caller
        MUST surface as a 5xx system error per R2 §4.7.
    """
    # Deduplicate when language == "en" so we don't generate
    # `language IN ('en','en')` (still correct, just noisy in EXPLAIN).
    languages = list({language, "en"})

    # CASE expression builds the 1-2-3-4 priority directly in SQL so the
    # query planner can use the composite index (company_id, kind,
    # language, status) without an extra application-side sort.
    priority = case(
        (
            and_(
                CompanyDocumentTemplate.company_id == company_id,
                CompanyDocumentTemplate.language == language,
            ),
            1,
        ),
        (
            and_(
                CompanyDocumentTemplate.company_id == company_id,
                CompanyDocumentTemplate.language == "en",
            ),
            2,
        ),
        (
            and_(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.language == language,
            ),
            3,
        ),
        (
            and_(
                CompanyDocumentTemplate.company_id.is_(None),
                CompanyDocumentTemplate.language == "en",
            ),
            4,
        ),
        # Should not be reachable: WHERE clause already restricts both
        # company_id and language to the four-stage subset, but a sane
        # else_ keeps the column NOT NULL on weird PG plans.
        else_=999,
    )

    stmt = (
        select(CompanyDocumentTemplate)
        .where(
            CompanyDocumentTemplate.kind == kind,
            CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
            or_(
                CompanyDocumentTemplate.company_id == company_id,
                CompanyDocumentTemplate.company_id.is_(None),
            ),
            CompanyDocumentTemplate.language.in_(languages),
        )
        .order_by(priority.asc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_template_html_cached(storage_prefix: str) -> str:
    """Fetch <storage_prefix>/template.html via the 5-min Redis cache (R2 §4.10).

    On hit: return the cached utf-8 string with no MinIO round-trip.
    On miss: read from MinIO, decode utf-8, write through the cache, return.

    The cache holds the decoded string (not raw bytes) because the Redis
    client in this stack runs with decode_responses=True; storing bytes
    would round-trip via str() and add no value over caching the decoded
    form directly.

    Raises:
        StorageNotFoundError: If template.html is missing in MinIO.
        StorageError: If the bucket itself is unavailable.
    """
    redis = get_redis()
    cache_key = _template_html_cache_key(storage_prefix)

    cached = await redis.get(cache_key)
    if cached is not None:
        return cached

    object_key = f"{storage_prefix}template.html"
    body_bytes = await get_object_bytes(object_key)
    body = body_bytes.decode("utf-8")

    await redis.setex(cache_key, _TEMPLATE_HTML_CACHE_TTL_SECONDS, body)

    logger.debug(
        "template_html_cache_miss",
        storage_prefix=storage_prefix,
        size=len(body),
    )
    return body


async def invalidate_template_html_cache(storage_prefix: str) -> None:
    """Drop the cached HTML body for one storage_prefix.

    Called by reconcile_templates / reconcile_platform_templates after
    moving a new template into place so the next render hits MinIO once
    and re-warms the cache (R2 §4.10).
    """
    redis = get_redis()
    cache_key = _template_html_cache_key(storage_prefix)
    await redis.delete(cache_key)
    logger.info(
        "template_html_cache_invalidated",
        storage_prefix=storage_prefix,
    )


def _resolve_asset_mime(filename: str) -> str:
    """Map a bare asset filename to its MIME type using the template-asset
    whitelist (R2 §4.4).

    Reconcile already validated this list when the template was activated,
    but we re-check here to defend against direct DB writes that bypass
    reconcile.

    Raises:
        BadRequestError: filename has no extension or its extension is
            not in TEMPLATE_ASSET_EXTENSION_TO_MIME.
    """
    if "." not in filename:
        raise BadRequestError(
            f"Template asset {filename!r} has no extension"
        )
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    mime = TEMPLATE_ASSET_EXTENSION_TO_MIME.get(ext)
    if mime is None:
        raise BadRequestError(
            f"Template asset {filename!r} has unsupported extension {ext!r}"
        )
    return mime


async def make_asset_data_uri_func(
    storage_prefix: str,
    asset_files: list[str],
) -> Callable[[str], str]:
    """Pre-fetch every binary asset for one template and return a sync
    callable suitable for a Jinja2 global (R2 §4.4).

    Why pre-fetch: Jinja2's default Environment renders synchronously,
    but storage.get_object_bytes is async. Pre-loading every asset into
    a dict before the renderer runs lets `asset_data_uri('logo.png')`
    inside the template stay sync -- one async pass at setup time, zero
    async I/O during render.

    The returned callable raises BadRequestError when called with a
    filename that wasn't declared in `asset_files`. This duplicates the
    Pydantic-driven check reconcile already performed, so a malicious or
    typo'd template can't reach into MinIO outside its asset set even if
    it slips past reconcile validation.

    SECURITY (SEC-NEW-01) -- TODO for R2 §2.4 (renderer rewrite):
        When the actual rendering code is built, the Jinja2 Environment
        used to render the template MUST be configured with:

            env = Environment(
                autoescape=True,        # XSS in HTML / PDF output
                undefined=StrictUndefined,  # explicit error on missing vars
            )

        autoescape protects against XSS when an investor-supplied field
        like `investor_name = "<script>alert(1)</script>"` flows into the
        HTML body. StrictUndefined turns silent placeholder typos into a
        loud failure during the render rather than producing a document
        with literal "{{ certificate_number }}" text. Neither setting
        affects this helper -- we only build the data URI dictionary
        here -- but they're required everywhere the dict is consumed.

    Args:
        storage_prefix: The MinIO folder path for this template.
            Must include the trailing slash; we append `filename` to it
            verbatim.
        asset_files: List of bare filenames (no path) declared on the
            CompanyDocumentTemplate row.

    Returns:
        A sync callable `(filename: str) -> str` that returns a
        ``data:<mime>;base64,<...>`` URI for one of the pre-loaded assets.

    Raises:
        BadRequestError: An asset filename has no / unsupported extension,
            or one of the assets is missing from MinIO at fetch time
            (StorageNotFoundError is wrapped to keep the Jinja2 surface
            uniform).
        StorageError: The bucket itself is unavailable.
    """
    cache: dict[str, str] = {}

    for filename in asset_files:
        if filename in cache:
            # Same asset listed twice -- skip the duplicate fetch.
            continue
        mime = _resolve_asset_mime(filename)
        object_key = f"{storage_prefix}{filename}"
        data = await get_object_bytes(object_key)
        b64 = base64.b64encode(data).decode("ascii")
        cache[filename] = f"data:{mime};base64,{b64}"

    def asset_data_uri(filename: str) -> str:
        """Resolve `filename` to an inline data URI.

        Raises:
            BadRequestError: filename was not part of asset_files. The
                template referenced an asset the row doesn't know about.
        """
        if filename not in cache:
            raise BadRequestError(
                f"Template asset {filename!r} is not declared in asset_files"
            )
        return cache[filename]

    return asset_data_uri


async def get_template(
    session: AsyncSession,
    company_id: UUID,
    template_id: UUID,
) -> CompanyDocumentTemplate:
    """Load one template, scoped so the caller's company sees its own
    rows AND the platform-default rows (company_id IS NULL).

    The platform-default scoping is intentional: staff inspecting a
    company's templates legitimately needs to see whatever rendering
    would actually use, including platform fallbacks for languages
    the company hasn't overridden.

    Args:
        session: Async DB session.
        company_id: Caller's company. The router validates it exists
            before reaching this helper.
        template_id: Template row id.

    Returns:
        The CompanyDocumentTemplate row.

    Raises:
        NotFoundError: The template doesn't exist, OR it belongs to a
            different (non-platform) company.
    """
    stmt = select(CompanyDocumentTemplate).where(
        CompanyDocumentTemplate.id == template_id,
        or_(
            CompanyDocumentTemplate.company_id == company_id,
            CompanyDocumentTemplate.company_id.is_(None),
        ),
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("Template not found")
    return template


async def list_templates(
    session: AsyncSession,
    company_id: UUID,
    *,
    kind: str | None = None,
    language: str | None = None,
    status: str | None = None,
) -> list[CompanyDocumentTemplate]:
    """List templates seen for a company.

    Returns:
      - All per-company rows matching the user-supplied filters.
      - Plus the platform-default `active` row for every (kind, language)
        pair NOT covered by a per-company `active` row -- so the staff
        view shows what the renderer would actually pick (R2 §4.5).

    "Covered" is decided independently of the user's status filter: it
    is always relative to per-company `active` rows, because that is the
    state the renderer cares about. The status filter only controls
    which per-company rows show up:

      status=None     -> all per-company rows + platform fallbacks
                         (for pairs not covered by an active per-company
                         row).
      status=active   -> active per-company rows + platform fallbacks
                         (for pairs without one).
      status=draft    -> draft per-company rows ONLY. Platform series
                         has no drafts -- including platform actives
                         here would mix two unrelated states.
      status=archived -> archived per-company rows ONLY. Same reasoning.

    Ordering: (kind ASC, language ASC, version DESC) so newest version
    of each (kind, language) sits at the top of its bucket; platform
    fallback rows are appended at the end of the list since they belong
    to a different scope conceptually.

    Args:
        session: Async DB session.
        company_id: The company whose templates we're listing. The
            router validates it exists before reaching this helper.
        kind: Optional kind filter applied to both branches.
        language: Optional language filter applied to both branches.
        status: Optional status filter; affects the per-company branch
            and gates platform fallback inclusion as documented above.

    Returns:
        A merged list of CompanyDocumentTemplate rows.
    """
    # -- Per-company branch --
    co_conditions = [CompanyDocumentTemplate.company_id == company_id]
    if kind is not None:
        co_conditions.append(CompanyDocumentTemplate.kind == kind)
    if language is not None:
        co_conditions.append(CompanyDocumentTemplate.language == language)
    if status is not None:
        co_conditions.append(CompanyDocumentTemplate.status == status)

    co_stmt = (
        select(CompanyDocumentTemplate)
        .where(*co_conditions)
        .order_by(
            CompanyDocumentTemplate.kind.asc(),
            CompanyDocumentTemplate.language.asc(),
            CompanyDocumentTemplate.version.desc(),
        )
    )
    co_rows = list((await session.execute(co_stmt)).scalars().all())

    # If the user asked for a non-active status, the platform-default
    # series is irrelevant -- it has no drafts or archived rows. Bail
    # out early.
    if status is not None and status != TemplateStatus.ACTIVE:
        return co_rows

    # Pairs already covered by a per-company active row -- platform
    # fallbacks for these are intentionally hidden so staff doesn't see
    # both lines for the same (kind, language).
    covered_pairs: set[tuple[str, str]] = {
        (row.kind, row.language)
        for row in co_rows
        if row.status == TemplateStatus.ACTIVE
    }

    # -- Platform-default branch (active rows only) --
    pf_conditions: list = [
        CompanyDocumentTemplate.company_id.is_(None),
        CompanyDocumentTemplate.status == TemplateStatus.ACTIVE,
    ]
    if kind is not None:
        pf_conditions.append(CompanyDocumentTemplate.kind == kind)
    if language is not None:
        pf_conditions.append(CompanyDocumentTemplate.language == language)

    pf_stmt = (
        select(CompanyDocumentTemplate)
        .where(*pf_conditions)
        .order_by(
            CompanyDocumentTemplate.kind.asc(),
            CompanyDocumentTemplate.language.asc(),
        )
    )
    pf_rows = [
        row
        for row in (await session.execute(pf_stmt)).scalars().all()
        if (row.kind, row.language) not in covered_pairs
    ]

    return co_rows + pf_rows
