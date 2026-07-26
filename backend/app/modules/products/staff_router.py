# =============================================================================
# AIVIS.ONE Backend -- Product Staff Router (Sprint 4.2 + Sprint 6.1 + F4.1
#                                            + Sprint 4.3)
# =============================================================================
#
# ENDPOINTS:
#   POST  /api/v1/staff/products                                    -- create
#   PATCH /api/v1/staff/products/{id}                                -- update
#   PATCH /api/v1/staff/products/{id}/status                         -- change status
#   POST  /api/v1/staff/products/{id}/installments                   -- add installment
#   PATCH /api/v1/staff/products/{id}/installments/{inst_id}         -- update installment
#   DELETE /api/v1/staff/products/{id}/installments/{inst_id}        -- soft-delete
#   POST  /api/v1/staff/products/{id}/installments/preview           -- calculator (B4)
#
# PERMISSIONS:
#   All endpoints require company_manage.
#   Create product, purchase_config update, and all installment ops
#   (including preview) also require financial_operations.
#
# Phase 4 FIX:
#   _require_financial_operations extracted to staff/permissions.py
#   (was duplicated in companies/staff_router.py).
#
# Sprint F4.1 CHANGES:
#   - Create/Update endpoints forward cover_url to the service layer.
#     cover_url is NOT financial_operations-gated (same tier as name /
#     description -- purely cosmetic media URL).
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - Create endpoint forwards body.package_size (renamed from body.units)
#     to create_product(package_size=...).
#
# Sprint 4.3 B4 (Installment Calculator):
#   - +POST /staff/products/{id}/installments/preview endpoint. Loads the
#     Product (for package_size + price_per_unit_cents), runs the pure
#     calculator function, returns the result. No DB writes -- this is
#     a read-only POST (POST chosen over GET only because the body
#     carries multiple structured parameters).
#   - Permission tier mirrors create_installment_endpoint: company_manage
#     plus financial_operations. Even though preview does not write
#     anything, exposing the calculator without financial_operations
#     would let a junior staff member shape investor offers without the
#     compliance gate.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit().
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import require_staff_permission
from app.modules.products.calculator import calculate_installment_preview
from app.modules.products.schemas import (
    CreateInstallmentRequest,
    CreateProductRequest,
    InstallmentPreviewRequest,
    InstallmentPreviewResponse,
    InstallmentResponse,
    ProductResponse,
    UpdateInstallmentRequest,
    UpdateProductRequest,
    UpdateProductStatusRequest,
)
from app.modules.products.service import (
    create_installment,
    create_product,
    delete_installment,
    get_product,
    update_installment,
    update_product,
    update_product_status,
)
from app.modules.staff.permissions import require_financial_operations
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/products", tags=["staff-products"])


# ---------------------------------------------------------------------------
# Product CRUD
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_endpoint(
    body: CreateProductRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> ProductResponse:
    """Create a new product.

    Requires: company_manage + financial_operations.
    """
    await require_financial_operations(staff, session)

    product = await create_product(
        body.company_id,
        body.name,
        body.package_size,
        staff,
        session,
        description=body.description,
        cover_url=body.cover_url,
        purchase_config=body.purchase_config,
    )
    return ProductResponse.model_validate(product)


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
)
async def update_product_endpoint(
    product_id: UUID,
    body: UpdateProductRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> ProductResponse:
    """Update product fields.

    If purchase_config is in the body, also requires financial_operations.
    """
    updates = body.model_dump(exclude_unset=True)

    if "purchase_config" in updates:
        await require_financial_operations(staff, session)

    product = await update_product(
        product_id,
        staff,
        session,
        name=updates.get("name"),
        description=updates.get("description", ...),
        cover_url=updates.get("cover_url", ...),
        purchase_config=updates.get("purchase_config", ...),
    )
    return ProductResponse.model_validate(product)


@router.patch(
    "/{product_id}/status",
    response_model=ProductResponse,
)
async def update_product_status_endpoint(
    product_id: UUID,
    body: UpdateProductStatusRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> ProductResponse:
    """Change product status."""
    product = await update_product_status(
        product_id, body.status, staff, session
    )
    return ProductResponse.model_validate(product)


# ---------------------------------------------------------------------------
# Installment CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/{product_id}/installments",
    response_model=InstallmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_installment_endpoint(
    product_id: UUID,
    body: CreateInstallmentRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> InstallmentResponse:
    """Add an installment plan template.

    Requires: company_manage + financial_operations.
    """
    await require_financial_operations(staff, session)

    installment = await create_installment(
        product_id, body.name, body.plan_config, staff, session
    )
    return InstallmentResponse.model_validate(installment)


@router.patch(
    "/{product_id}/installments/{installment_id}",
    response_model=InstallmentResponse,
)
async def update_installment_endpoint(
    product_id: UUID,
    installment_id: UUID,
    body: UpdateInstallmentRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> InstallmentResponse:
    """Update an installment plan template.

    Requires: company_manage + financial_operations.
    """
    await require_financial_operations(staff, session)

    updates = body.model_dump(exclude_unset=True)

    installment = await update_installment(
        product_id,
        installment_id,
        staff,
        session,
        name=updates.get("name"),
        plan_config=updates.get("plan_config"),
    )
    return InstallmentResponse.model_validate(installment)


@router.delete(
    "/{product_id}/installments/{installment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_installment_endpoint(
    product_id: UUID,
    installment_id: UUID,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete an installment plan template.

    Requires: company_manage + financial_operations.
    """
    await require_financial_operations(staff, session)

    await delete_installment(product_id, installment_id, staff, session)


# ---------------------------------------------------------------------------
# Installment Calculator (Sprint 4.3 B4)
# ---------------------------------------------------------------------------


@router.post(
    "/{product_id}/installments/preview",
    response_model=InstallmentPreviewResponse,
)
async def preview_installment_endpoint(
    product_id: UUID,
    body: InstallmentPreviewRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> InstallmentPreviewResponse:
    """Compute a motivational installment plan_config from staff inputs.

    Requires: company_manage + financial_operations.

    Read-only: no DB writes. The returned plan_config is the same
    shape consumed by POST /staff/products/{id}/installments -- staff
    inspects, optionally edits bonus_units / agent_bonus_units, then
    submits the same plan_config to the create endpoint. One algorithm
    in one language -- no JS / Python drift.
    """
    await require_financial_operations(staff, session)

    product = await get_product(product_id, session)

    result = calculate_installment_preview(
        package_size=product.package_size,
        price_per_unit_cents=product.price_per_unit_cents,
        num_tranches=body.num_tranches,
        last_tranche_percent=body.last_tranche_percent,
        amount_rounding_cents=body.amount_rounding_cents,
    )

    return InstallmentPreviewResponse.model_validate(result)
