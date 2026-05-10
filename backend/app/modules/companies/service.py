# =============================================================================
# CBSHOME Backend -- Company Service (Sprint 4.1 + Sprint F4.1 + F4.1.1 hotfix
#                                       + Sprint 4.3 + Refactor 2 iter 2.2)
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

from uuid import UUID, uuid4

import mimetypes

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.storage import (
    delete_object,
    upload_object,
)
from app.modules.auth.service import hash_password, get_platform_user_id
from app.modules.companies.constants import (
    ALLOWED_ATTACHMENT_MIME_TYPES,
    VALID_COMPANY_STATUS_TRANSITIONS,
    validate_distribution_config,
)
from app.modules.companies.models import (
    CompanyAttachment,
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
    file_bytes: bytes,
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

    Raises:
        NotFoundError: If the company doesn't exist.
        StorageError: On any MinIO failure (bubbled up from upload_object).
    """
    await get_company(company_id, session)

    attachment_id = uuid4()
    storage_key = build_storage_key(company_id, attachment_id, original_filename)

    # Upload to MinIO first. A subsequent transaction rollback leaves an
    # orphan that reconcile_attachments will reap.
    await upload_object(storage_key, file_bytes, content_type)

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
        file_size_bytes=len(file_bytes),
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
            "file_size_bytes": len(file_bytes),
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
        size=len(file_bytes),
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
    file_bytes: bytes,
    original_filename: str,
    content_type: str,
) -> CompanyAttachment:
    """Swap the binary content of an existing attachment.

    Old MinIO object is deleted, the new one is uploaded under a fresh
    storage_key (the attachment_id stays, so the path prefix is stable
    but the trailing filename changes when `original_filename` changes).
    Metadata fields other than storage_key / mime_type / file_size_bytes
    / original_filename are untouched.

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
    await upload_object(new_storage_key, file_bytes, content_type)
    if old_storage_key != new_storage_key:
        # delete_object is idempotent on a missing key, so a previous
        # partial replace that already removed the old object will not
        # error here.
        await delete_object(old_storage_key)

    attachment.storage_key = new_storage_key
    attachment.original_filename = original_filename
    attachment.mime_type = content_type
    attachment.file_size_bytes = len(file_bytes)

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
            "file_size_bytes": len(file_bytes),
        },
    )

    logger.info(
        "attachment_replaced",
        attachment_id=str(attachment.id),
        company_id=str(company_id),
        staff_id=str(staff.id),
        old_storage_key=old_storage_key,
        new_storage_key=new_storage_key,
        size=len(file_bytes),
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
