# =============================================================================
# AIVIS.ONE Backend -- Product Service (Sprint 4.2 + Sprint 6.1 + Sprint F4.1
#                                       + Sprint 4.3)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_product()        -- create Product, copy price from Company,
#                              attach to active OptionPool (Sprint 4.3)
#   update_product()        -- partial update (name, description,
#                              purchase_config)
#   set_product_cover()     -- H36: upload / replace the cover file
#   delete_product_cover()  -- H36: remove the cover file
#   update_product_status() -- state machine transition
#   get_product()           -- load Product by id
#   list_products()         -- paginated list (public: active only)
#   get_product_detail()    -- product + non-deleted installments
#   create_installment()    -- add installment template, validate plan_config
#   update_installment()    -- update template, re-validate plan_config
#   delete_installment()    -- soft-delete (is_deleted=True)
#   cascade_price()         -- update price on products + soft-delete installments
#
# Sprint 6.1 CHANGES:
#   - create_product(): gift_units -> purchase_config
#   - update_product(): gift_units -> purchase_config (set_jsonb)
#   - validate_purchase_config() called on save
#
# Sprint F4.1 CHANGES:
#   - create_product(): +cover_url kwarg (scalar, stored as-is).
#   - update_product(): +cover_url sentinel kwarg (Ellipsis semantics).
#
# H36 P-131 CHANGES (pictures in our storage):
#   - cover_url left create_product() / update_product(). The cover is a
#     file in our storage under companies/<company_id>/products/<id>/,
#     set by set_product_cover() and removed by delete_product_cover();
#     Product.cover_storage_key holds its key (companies/media.py).
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - create_product(): kwarg `units` -> `package_size`. Looks up the
#     single active OptionPool for the company, sets pool_id from it,
#     and validates package_size <= pool.total_options. If the company
#     has no active pool yet, the request is rejected with 400.
#   - validate_plan_config() call sites now pass product.package_size
#     (the column was renamed). The kwarg name stays as `product_units`
#     in constants.py to avoid touching every test fixture (see comment
#     in constants.py).
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# JSONB RULE:
#   plan_config and purchase_config updated via set_jsonb(). Never direct assign.
#
# PRICE:
#   Product.price_per_unit_cents is denormalized from Company.
#   Set at creation, updated only via cascade_price() on company price change.
#   Never set directly by staff.
# =============================================================================

from uuid import UUID

import structlog
from datetime import datetime, UTC
from typing import BinaryIO

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.storage import StorageError, delete_object, upload_object
from app.modules.companies.constants import ROADMAP_COVER_MAX_BYTES
from app.modules.companies.media import product_cover_key, validate_media_upload
from app.modules.companies.models import CompanyProfile
from app.modules.companies.service import get_company
from app.modules.products.constants import (
    VALID_PRODUCT_STATUS_TRANSITIONS,
    validate_plan_config,
)
from app.modules.products.models import (
    Product,
    ProductInstallment,
    ProductStatus,
)
from app.modules.users.models import User

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------


async def create_product(
    company_id: UUID,
    name: str,
    package_size: int,
    staff: User,
    session: AsyncSession,
    *,
    description: str | None = None,
    purchase_config: dict | None = None,  # type: ignore[type-arg]
) -> Product:
    """Create a new product for a company.

    Copies price_per_unit_cents from CompanyProfile.
    If purchase_config is provided, validates it before saving.

    Sprint 4.3: looks up the company's single active OptionPool, attaches
    the product to it, and validates package_size <= pool.total_options.

    Raises:
        NotFoundError: If company not found.
        BadRequestError: If purchase_config is invalid, the company has
            no active pool, or package_size exceeds pool.total_options.
        RuntimeError: If the company has multiple active pools (data
            integrity violation; the partial unique index should prevent
            this, but we surface it explicitly).
    """
    # Local import: avoids a top-level circular dependency between
    # products and pools (pools/service.py is the canonical lookup site,
    # but it imports nothing from products at the top level).
    from app.modules.pools.service import get_active_pool

    company = await get_company(company_id, session)

    if purchase_config is not None:
        from app.modules.processors.validators import validate_purchase_config
        validate_purchase_config(purchase_config)

    # Sprint 4.3: every product must belong to an active pool.
    pool = await get_active_pool(company.id, session)

    # Idiot-check: a single package must fit in the pool. This is a
    # static guard at creation time; runtime availability is checked in
    # purchases/service._get_pool_remaining (which accounts for already
    # consumed options).
    if package_size > pool.total_options:
        raise BadRequestError(
            f"package_size ({package_size}) exceeds pool.total_options "
            f"({pool.total_options}) for company {company.id}"
        )

    product = Product(
        pool_id=pool.id,
        company_id=company.id,
        name=name,
        description=description,
        package_size=package_size,
        purchase_config=purchase_config,
        price_per_unit_cents=company.price_per_unit_cents,
        status=ProductStatus.HIDDEN,
    )
    session.add(product)
    await session.flush()
    await session.refresh(product)

    # Audit.
    await record_audit(
        session=session,
        event="product.created",
        actor_id=staff.id,
        actor_type="staff",
        target_type="product",
        target_id=product.id,
        data={
            "company_id": str(company_id),
            "pool_id": str(pool.id),
            "name": name,
            "package_size": package_size,
        },
    )

    logger.info(
        "product_created",
        product_id=str(product.id),
        company_id=str(company_id),
        pool_id=str(pool.id),
        package_size=package_size,
        staff_id=str(staff.id),
    )

    return product


async def update_product(
    product_id: UUID,
    staff: User,
    session: AsyncSession,
    *,
    name: str | None = None,
    description=...,
    purchase_config=...,
) -> Product:
    """Partial update of product fields.

    Uses Ellipsis (...) as the "not provided" sentinel to distinguish
    between "keep current value" and "set to null" for nullable fields.

    Raises:
        NotFoundError: If product not found.
        BadRequestError: If purchase_config is invalid.
    """
    product = await get_product(product_id, session)

    changed_fields = []

    if name is not None:
        product.name = name
        changed_fields.append("name")

    if description is not ...:
        product.description = description
        changed_fields.append("description")

    if purchase_config is not ...:
        if purchase_config is not None:
            from app.modules.processors.validators import validate_purchase_config
            validate_purchase_config(purchase_config)
        product.set_jsonb("purchase_config", purchase_config)
        changed_fields.append("purchase_config")

    if changed_fields:
        await session.flush()
        await session.refresh(product)

        # Audit.
        await record_audit(
            session=session,
            event="product.updated",
            actor_id=staff.id,
            actor_type="staff",
            target_type="product",
            target_id=product.id,
            data={"fields": changed_fields},
        )

    return product


async def update_product_status(
    product_id: UUID,
    new_status: str,
    staff: User,
    session: AsyncSession,
) -> Product:
    """Change product status via state machine.

    Raises:
        NotFoundError: If product not found.
        BadRequestError: If transition is invalid.
    """
    product = await get_product(product_id, session)

    allowed = VALID_PRODUCT_STATUS_TRANSITIONS.get(product.status, frozenset())
    if new_status not in allowed:
        raise BadRequestError(
            f"Cannot transition from '{product.status}' to '{new_status}'"
        )

    old_status = product.status
    product.status = new_status
    await session.flush()
    await session.refresh(product)

    # Audit.
    await record_audit(
        session=session,
        event="product.status_changed",
        actor_id=staff.id,
        actor_type="staff",
        target_type="product",
        target_id=product.id,
        data={"old_status": old_status, "new_status": new_status},
    )

    return product


async def _get_company_product(
    company_id: UUID, product_id: UUID, session: AsyncSession
) -> Product:
    """The product, when it belongs to `company_id`; 404 otherwise.

    A product of another company answers exactly like a missing one, so
    the cover routes cannot be used to probe ids across projects.
    """
    await get_company(company_id, session)
    product = await get_product(product_id, session)
    if product.company_id != company_id:
        raise NotFoundError("Product not found")
    return product


async def set_product_cover(
    session: AsyncSession,
    company_id: UUID,
    product_id: UUID,
    staff: User,
    *,
    file_data: BinaryIO,
    file_size_bytes: int,
    content_type: str,
    file_extension: str,
) -> Product:
    """Upload / replace the cover of a product (H36 P-131, staff).

    The object goes to companies/<company_id>/products/<product_id>/
    (product_cover_key). Same storage flow as the roadmap cover
    (companies/service.py::set_roadmap_cover): upload before the row is
    written; a replace with another extension deletes the old object
    best-effort after the flush. Limit ROADMAP_COVER_MAX_BYTES.

    Raises:
        BadRequestError: extension, type or size refused
            (validate_media_upload), checked before anything is written.
        NotFoundError: company or product not found, or the product is
            another company's.
        StorageError: the upload failed; nothing was written.
    """
    validate_media_upload(
        content_type=content_type,
        file_extension=file_extension,
        file_size_bytes=file_size_bytes,
        max_bytes=ROADMAP_COVER_MAX_BYTES,
    )
    product = await _get_company_product(company_id, product_id, session)

    old_storage_key = product.cover_storage_key
    new_storage_key = product_cover_key(company_id, product_id, file_extension)

    await upload_object(
        new_storage_key,
        file_data,
        content_type,
        content_length=file_size_bytes,
    )

    product.cover_storage_key = new_storage_key
    await session.flush()
    await session.refresh(product)

    if old_storage_key and old_storage_key != new_storage_key:
        try:
            await delete_object(old_storage_key)
        except StorageError as exc:
            logger.warning(
                "product_cover_old_delete_failed",
                product_id=str(product_id),
                storage_key=old_storage_key,
                error=str(exc),
            )

    await record_audit(
        session=session,
        event="product.cover_uploaded",
        actor_id=staff.id,
        actor_type="staff",
        target_type="product",
        target_id=product.id,
        data={
            "company_id": str(company_id),
            "storage_key": new_storage_key,
            "content_type": content_type,
            "file_size_bytes": file_size_bytes,
        },
    )

    logger.info(
        "product_cover_uploaded",
        product_id=str(product.id),
        company_id=str(company_id),
        staff_id=str(staff.id),
        storage_key=new_storage_key,
        size=file_size_bytes,
    )

    return product


async def delete_product_cover(
    company_id: UUID,
    product_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Remove the cover of a product (H36 P-131, staff).

    404 when no cover is set, as for the roadmap cover. The object delete
    is best-effort.

    Raises:
        NotFoundError: company or product not found, the product is
            another company's, or it has no cover.
    """
    product = await _get_company_product(company_id, product_id, session)

    if product.cover_storage_key is None:
        raise NotFoundError("Product has no cover image")

    storage_key = product.cover_storage_key
    product.cover_storage_key = None
    await session.flush()

    try:
        await delete_object(storage_key)
    except StorageError as exc:
        logger.warning(
            "product_cover_delete_failed",
            product_id=str(product_id),
            storage_key=storage_key,
            error=str(exc),
        )

    await record_audit(
        session=session,
        event="product.cover_deleted",
        actor_id=staff.id,
        actor_type="staff",
        target_type="product",
        target_id=product.id,
        data={"company_id": str(company_id), "storage_key": storage_key},
    )


async def get_product(
    product_id: UUID,
    session: AsyncSession,
) -> Product:
    """Load Product by id.

    Raises:
        NotFoundError: If product not found.
    """
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        raise NotFoundError("Product not found")

    return product


async def list_products(
    session: AsyncSession,
    *,
    active_only: bool = True,
    company_id: UUID | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Product], int]:
    """List products with pagination.

    active_only=True for public endpoint (only active products).
    active_only=False for staff endpoint (all products).
    Optional company_id filter.

    Returns (products, total_count).
    """
    conditions = []
    if active_only:
        conditions.append(Product.status == ProductStatus.ACTIVE)
    if company_id is not None:
        conditions.append(Product.company_id == company_id)

    where_clause = True if not conditions else conditions[0]
    for cond in conditions[1:]:
        where_clause = where_clause & cond

    # Count total.
    count_stmt = select(func.count()).select_from(Product).where(where_clause)
    total = (await session.execute(count_stmt)).scalar_one()

    # Fetch page.
    offset = (page - 1) * per_page
    stmt = (
        select(Product)
        .where(where_clause)
        .order_by(Product.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    products = list(result.scalars().all())

    return products, total


async def get_product_detail(
    product_id: UUID,
    session: AsyncSession,
) -> tuple[Product, list[ProductInstallment]]:
    """Load product with non-deleted installment plans.

    Raises:
        NotFoundError: If product not found.
    """
    product = await get_product(product_id, session)

    stmt = (
        select(ProductInstallment)
        .where(
            ProductInstallment.product_id == product_id,
            ProductInstallment.is_deleted == False,  # noqa: E712
        )
        .order_by(ProductInstallment.created_at.asc())
    )
    result = await session.execute(stmt)
    installments = list(result.scalars().all())

    return product, installments


# ---------------------------------------------------------------------------
# Installment CRUD
# ---------------------------------------------------------------------------


async def create_installment(
    product_id: UUID,
    name: str,
    plan_config: dict,  # type: ignore[type-arg]
    staff: User,
    session: AsyncSession,
) -> ProductInstallment:
    """Add an installment plan template to a product.

    Validates plan_config against product and company context.

    Raises:
        NotFoundError: If product not found.
        BadRequestError: If plan_config is invalid.
    """
    product = await get_product(product_id, session)

    # Validate plan_config against product context.
    # Sprint 4.3: column renamed `units` -> `package_size`. The kwarg name
    # `product_units` stays for backwards compat with test fixtures.
    validate_plan_config(
        plan_config,
        product_units=product.package_size,
        price_per_unit_cents=product.price_per_unit_cents,
    )

    installment = ProductInstallment(
        product_id=product.id,
        name=name,
        plan_config=plan_config,
    )
    session.add(installment)
    await session.flush()
    await session.refresh(installment)

    # Audit.
    await record_audit(
        session=session,
        event="product.installment_created",
        actor_id=staff.id,
        actor_type="staff",
        target_type="product_installment",
        target_id=installment.id,
        data={"product_id": str(product_id), "name": name},
    )

    return installment


async def update_installment(
    product_id: UUID,
    installment_id: UUID,
    staff: User,
    session: AsyncSession,
    *,
    name: str | None = None,
    plan_config: dict | None = None,  # type: ignore[type-arg]
) -> ProductInstallment:
    """Update an installment plan template.

    If plan_config is provided, re-validates against product context.

    Raises:
        NotFoundError: If product or installment not found.
        BadRequestError: If plan_config is invalid.
    """
    product = await get_product(product_id, session)
    installment = await _get_installment(product_id, installment_id, session)

    changed_fields = []

    if name is not None:
        installment.name = name
        changed_fields.append("name")

    if plan_config is not None:
        # Sprint 4.3: same rename note as in create_installment.
        validate_plan_config(
            plan_config,
            product_units=product.package_size,
            price_per_unit_cents=product.price_per_unit_cents,
        )
        installment.set_jsonb("plan_config", plan_config)
        changed_fields.append("plan_config")

    if changed_fields:
        await session.flush()
        await session.refresh(installment)

        # Audit.
        await record_audit(
            session=session,
            event="product.installment_updated",
            actor_id=staff.id,
            actor_type="staff",
            target_type="product_installment",
            target_id=installment.id,
            data={
                "product_id": str(product_id),
                "fields": changed_fields,
            },
        )

    return installment


async def delete_installment(
    product_id: UUID,
    installment_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Soft-delete an installment plan template.

    Raises:
        NotFoundError: If product or installment not found.
    """
    await get_product(product_id, session)
    installment = await _get_installment(product_id, installment_id, session)

    installment.is_deleted = True
    await session.flush()

    # Audit.
    await record_audit(
        session=session,
        event="product.installment_deleted",
        actor_id=staff.id,
        actor_type="staff",
        target_type="product_installment",
        target_id=installment.id,
        data={"product_id": str(product_id)},
    )


# ---------------------------------------------------------------------------
# Price cascade (called from companies/service.py)
# ---------------------------------------------------------------------------


async def cascade_price(
    company_id: UUID,
    new_price: int,
    session: AsyncSession,
) -> int:
    """Update price on all active/hidden products and soft-delete their installments.

    Called by companies/service.py via _apply_price_change(), which
    both the STAFF price endpoint (update_price) and the project's own
    self-service edit (update_own_company, TASK-39 item 6) go through.

    Returns number of products updated.
    """
    # Find active/hidden products for this company.
    product_stmt = select(Product.id).where(
        Product.company_id == company_id,
        Product.status.in_([ProductStatus.ACTIVE, ProductStatus.HIDDEN]),
    )
    result = await session.execute(product_stmt)
    product_ids = [row[0] for row in result.all()]

    if not product_ids:
        return 0

    # Update price on products.
    update_stmt = (
        update(Product)
        .where(Product.id.in_(product_ids))
        .values(price_per_unit_cents=new_price, updated_at=datetime.now(UTC))
    )
    await session.execute(update_stmt)

    # Soft-delete all installment templates for these products.
    installment_stmt = (
        update(ProductInstallment)
        .where(
            ProductInstallment.product_id.in_(product_ids),
            ProductInstallment.is_deleted == False,  # noqa: E712
        )
        .values(is_deleted=True)
    )
    await session.execute(installment_stmt)

    return len(product_ids)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_installment(
    product_id: UUID,
    installment_id: UUID,
    session: AsyncSession,
) -> ProductInstallment:
    """Load a non-deleted installment by product and installment ID.

    Raises:
        NotFoundError: If installment not found or soft-deleted.
    """
    stmt = select(ProductInstallment).where(
        ProductInstallment.id == installment_id,
        ProductInstallment.product_id == product_id,
        ProductInstallment.is_deleted == False,  # noqa: E712
    )
    result = await session.execute(stmt)
    installment = result.scalar_one_or_none()

    if installment is None:
        raise NotFoundError("Installment plan not found")

    return installment
