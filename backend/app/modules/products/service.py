# =============================================================================
# CBSHOME Backend -- Product Service (Sprint 4.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_product()        -- create Product, copy price from Company
#   update_product()        -- partial update (name, description, gift_units)
#   update_product_status() -- state machine transition
#   get_product()           -- load Product by id
#   list_products()         -- paginated list (public: active only)
#   get_product_detail()    -- product + non-deleted installments
#   create_installment()    -- add installment template, validate plan_config
#   update_installment()    -- update template, re-validate plan_config
#   delete_installment()    -- soft-delete (is_deleted=True)
#   cascade_price()         -- update price on products + soft-delete installments
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# JSONB RULE:
#   plan_config updated via set_jsonb(). Never direct assign.
#
# PRICE:
#   Product.price_per_unit_cents is denormalized from Company.
#   Set at creation, updated only via cascade_price() on company price change.
#   Never set directly by staff.
# =============================================================================

from uuid import UUID

import structlog
from datetime import datetime, UTC
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, NotFoundError
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
    units: int,
    staff: User,
    session: AsyncSession,
    *,
    description: str | None = None,
    gift_units: int = 0,
) -> Product:
    """Create a new product for a company.

    Copies price_per_unit_cents from CompanyProfile.

    Raises:
        NotFoundError: If company not found.
    """
    company = await get_company(company_id, session)

    product = Product(
        company_id=company.id,
        name=name,
        description=description,
        units=units,
        gift_units=gift_units,
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
            "name": name,
            "units": units,
        },
    )

    logger.info(
        "product_created",
        product_id=str(product.id),
        company_id=str(company_id),
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
    gift_units: int | None = None,
) -> Product:
    """Partial update of product fields.

    Raises:
        NotFoundError: If product not found.
    """
    product = await get_product(product_id, session)

    changed_fields = []

    if name is not None:
        product.name = name
        changed_fields.append("name")

    if description is not ...:
        product.description = description
        changed_fields.append("description")

    if gift_units is not None:
        product.gift_units = gift_units
        changed_fields.append("gift_units")

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
    validate_plan_config(
        plan_config,
        product_units=product.units,
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
        validate_plan_config(
            plan_config,
            product_units=product.units,
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

    Called by companies/service.py update_price().

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
