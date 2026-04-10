# =============================================================================
# CBSHOME Backend -- Company Staff Router (Sprint 4.1, fix Phase 4)
# =============================================================================
#
# ENDPOINTS:
#   POST  /api/v1/staff/companies                          -- create company
#   PATCH /api/v1/staff/companies/{id}                     -- update profile
#   PATCH /api/v1/staff/companies/{id}/price               -- change price
#   POST  /api/v1/staff/companies/{id}/roadmap             -- add roadmap item
#   PATCH /api/v1/staff/companies/{id}/roadmap/{item_id}   -- update roadmap item
#   DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}  -- soft-delete item
#   PATCH /api/v1/staff/companies/{id}/roadmap/reorder     -- reorder items
#
# PERMISSIONS:
#   All endpoints require company_manage permission.
#   Create, price change, and distribution_config update also require
#   financial_operations permission.
#
# Phase 4 FIX:
#   _require_permission / _require_financial_operations extracted to
#   staff/permissions.py (was duplicated in products/staff_router.py).
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import (
    get_current_user_write,
    require_staff_permission,
)
from app.modules.companies.schemas import (
    CompanyDetailResponse,
    CompanyListResponse,
    CompanyResponse,
    CreateCompanyRequest,
    CreateRoadmapItemRequest,
    ReorderRoadmapRequest,
    RoadmapItemResponse,
    UpdateCompanyRequest,
    UpdatePriceRequest,
    UpdateRoadmapItemRequest,
)
from app.modules.companies.service import (
    create_company,
    create_roadmap_item,
    delete_roadmap_item,
    get_company_detail,
    list_companies,
    reorder_roadmap,
    update_company,
    update_price,
    update_roadmap_item,
)
from app.modules.staff.constants import is_admin
from app.modules.staff.permissions import require_financial_operations
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/companies", tags=["staff-companies"])


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_endpoint(
    body: CreateCompanyRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Create a new company (user + profile).

    Requires: company_manage + financial_operations.
    """
    await require_financial_operations(staff, session)

    profile = await create_company(body, staff, session)
    return CompanyResponse.model_validate(profile)


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
)
async def update_company_endpoint(
    company_id: UUID,
    body: UpdateCompanyRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Update company profile.

    If distribution_config is in the body, also requires financial_operations.
    """
    updates = body.model_dump(exclude_unset=True)
    if "distribution_config" in updates:
        await require_financial_operations(staff, session)

    profile = await update_company(company_id, body, staff, session)
    return CompanyResponse.model_validate(profile)


@router.patch(
    "/{company_id}/price",
    response_model=CompanyResponse,
)
async def update_price_endpoint(
    company_id: UUID,
    body: UpdatePriceRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Change company share price.

    Requires: company_manage + financial_operations.
    Cascades to active/hidden products.
    """
    await require_financial_operations(staff, session)

    profile = await update_price(company_id, body.price_per_unit_cents, staff, session)
    return CompanyResponse.model_validate(profile)


# ---------------------------------------------------------------------------
# Roadmap CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/{company_id}/roadmap",
    response_model=RoadmapItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_roadmap_item_endpoint(
    company_id: UUID,
    body: CreateRoadmapItemRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Add a roadmap milestone to a company."""
    item = await create_roadmap_item(
        company_id,
        body.title,
        staff,
        session,
        description=body.description,
        target_date=body.target_date,
        status=body.status,
    )
    return RoadmapItemResponse.model_validate(item)


# NOTE: reorder MUST be declared before {item_id} routes to prevent
# FastAPI from matching "reorder" as a UUID path parameter.
@router.patch(
    "/{company_id}/roadmap/reorder",
    response_model=list[RoadmapItemResponse],
)
async def reorder_roadmap_endpoint(
    company_id: UUID,
    body: ReorderRoadmapRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> list[RoadmapItemResponse]:
    """Reorder roadmap items."""
    items = await reorder_roadmap(company_id, body.item_ids, staff, session)
    return [RoadmapItemResponse.model_validate(item) for item in items]


@router.patch(
    "/{company_id}/roadmap/{item_id}",
    response_model=RoadmapItemResponse,
)
async def update_roadmap_item_endpoint(
    company_id: UUID,
    item_id: UUID,
    body: UpdateRoadmapItemRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Update a roadmap item (partial)."""
    updates = body.model_dump(exclude_unset=True)

    item = await update_roadmap_item(
        company_id,
        item_id,
        staff,
        session,
        title=updates.get("title"),
        description=updates.get("description", ...),
        target_date=updates.get("target_date", ...),
        status=updates.get("status"),
    )
    return RoadmapItemResponse.model_validate(item)


@router.delete(
    "/{company_id}/roadmap/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_roadmap_item_endpoint(
    company_id: UUID,
    item_id: UUID,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete a roadmap item."""
    await delete_roadmap_item(company_id, item_id, staff, session)
