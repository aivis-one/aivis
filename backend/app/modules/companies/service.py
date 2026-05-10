# =============================================================================
# CBSHOME Backend -- Company Service (Sprint 4.1 + Sprint F4.1 + F4.1.1 hotfix
#                                       + Sprint 4.3 + Refactor 2 iter 2.2 + 2.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_company()       -- create User (role=company) + CompanyProfile
#                             with total_supply / shares_per_option
#   update_company()       -- partial update profile/media/distribution_config
#                             (NO supply fields here -- see Sprint 4.3 note)
#   update_price()         -- change price + cascade to Products + history
#   get_company()          -- load CompanyProfile by id
#   list_companies()       -- paginated list (public: active only; staff: all;
#                             optional case-insensitive name search)
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
from collections.abc import Callable
from typing import BinaryIO
from uuid import UUID, uuid4

import structlog
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.redis import get_redis
from app.core.storage import (
    delete_object,
    get_object_bytes,
    upload_object,
)
from app.modules.auth.service import hash_password, get_platform_user_id
from app.modules.companies.constants import (
    ALLOWED_ATTACHMENT_MIME_TYPES,
    DocumentTemplateKind,
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
    AttachmentInboxMetadata,
    AttachmentPatchBody,
    CreateCompanyRequest,
    UpdateCompanyRequest,
)
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
    password_hash = hash_password(body.password)
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
        if "company_profiles_user_id_key" in str(exc.orig):
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
    search: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[CompanyProfile], int]:
    """List companies with pagination.

    active_only=True for public endpoint (only active companies).
    active_only=False for staff endpoint (all companies).
    search: optional case-insensitive substring match on name. LIKE
            metacharacters in the needle are escaped so a user query
            like "50%" matches the literal "50%" rather than acting
            as a wildcard.

    Returns (companies, total_count).
    """
    conditions = []
    if active_only:
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


async def get_company_detail(
    company_id: UUID,
    session: AsyncSession,
) -> tuple[CompanyProfile, list[CompanyRoadmapItem]]:
    """Load company profile with roadmap items (sorted by order).

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

    return profile, roadmap_items


# ---------------------------------------------------------------------------
# Roadmap CRUD
# ---------------------------------------------------------------------------


async def create_roadmap_item(
    company_id: UUID,
    title: str,
    staff: User,
    session: AsyncSession,
    *,
    description: str | None = None,
    target_date=None,
    status: str | None = None,
) -> CompanyRoadmapItem:
    """Add a roadmap milestone to a company.

    New items are placed at the end (max order + 1).

    Raises:
        NotFoundError: If company not found.
        BadRequestError: If status is invalid.
    """
    # Verify company exists.
    await get_company(company_id, session)

    # Validate status if provided.
    if status is not None:
        valid_statuses = {s.value for s in RoadmapItemStatus}
        if status not in valid_statuses:
            raise BadRequestError(
                f"Invalid roadmap item status: '{status}'. "
                f"Valid: {valid_statuses}"
            )

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
        title=title,
        description=description,
        target_date=target_date,
        status=status or RoadmapItemStatus.PLANNED,
        order=max_order + 1,
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
        data={"company_id": str(company_id), "title": title},
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
    status: str | None = None,
) -> CompanyRoadmapItem:
    """Partial update of a roadmap item.

    Raises:
        NotFoundError: If company or item not found.
        BadRequestError: If status is invalid.
    """
    # Verify company exists.
    await get_company(company_id, session)

    item = await _get_roadmap_item(company_id, item_id, session)

    changed_fields = []

    if title is not None:
        item.title = title
        changed_fields.append("title")

    if description is not ...:
        item.description = description
        changed_fields.append("description")

    if target_date is not ...:
        item.target_date = target_date
        changed_fields.append("target_date")

    if status is not None:
        valid_statuses = {s.value for s in RoadmapItemStatus}
        if status not in valid_statuses:
            raise BadRequestError(
                f"Invalid roadmap item status: '{status}'. "
                f"Valid: {valid_statuses}"
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


def build_storage_key(company_id: UUID, attachment_id: UUID, filename: str) -> str:
    """Build the canonical MinIO key for an attachment object.

    Mirrors the convention used by reconcile_attachments.py so direct DB
    inserts and inbox-driven inserts produce identical keys.

    Round 4 (QC-01): public name -- the reconcile script imports this
    helper directly and the underscore prefix would falsely signal an
    internal-only contract.
    """
    return f"companies/{company_id}/attachments/{attachment_id}/{filename}"


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
    guess, _ = mimetypes.guess_type(filename)
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
