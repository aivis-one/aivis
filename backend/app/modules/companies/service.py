# =============================================================================
# CBSHOME Backend -- Company Service (Sprint 4.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_company()       -- create User (role=company) + CompanyProfile
#   update_company()       -- partial update profile/media/distribution_config
#   update_price()         -- change price + cascade to Products + history
#   get_company()          -- load CompanyProfile by id
#   list_companies()       -- paginated list (public: active only; staff: all)
#   get_company_detail()   -- profile + roadmap items
#   create_roadmap_item()  -- add roadmap milestone
#   update_roadmap_item()  -- partial update roadmap item
#   delete_roadmap_item()  -- soft-delete (is_deleted=True)
#   reorder_roadmap()      -- bulk update order column
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
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.auth.service import hash_password, get_platform_user_id
from app.modules.companies.constants import (
    VALID_COMPANY_STATUS_TRANSITIONS,
    validate_distribution_config,
)
from app.modules.companies.models import (
    CompanyPriceHistory,
    CompanyProfile,
    CompanyRoadmapItem,
    CompanyStatus,
    RoadmapItemStatus,
)
from app.modules.companies.schemas import (
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
        data={"name": body.name, "user_id": str(company_user.id)},
    )

    logger.info(
        "company_created",
        company_id=str(profile.id),
        user_id=str(company_user.id),
        staff_id=str(staff.id),
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


async def list_companies(
    session: AsyncSession,
    *,
    active_only: bool = True,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[CompanyProfile], int]:
    """List companies with pagination.

    active_only=True for public endpoint (only active companies).
    active_only=False for staff endpoint (all companies).

    Returns (companies, total_count).
    """
    base_filter = CompanyProfile.status == CompanyStatus.ACTIVE if active_only else True

    # Count total.
    count_stmt = select(func.count()).select_from(CompanyProfile).where(base_filter)
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(CompanyProfile)
        .where(base_filter)
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
