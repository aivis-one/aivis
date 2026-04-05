# =============================================================================
# CBSHOME Backend -- Company Public Router (Sprint 4.1)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/companies       -- list active companies (public)
#   GET /api/v1/companies/{id}  -- company detail with roadmap (public)
#
# AUTH:
#   No authentication required. Public storefront.
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.companies.schemas import (
    PublicCompanyDetailResponse,
    PublicCompanyListResponse,
    PublicCompanyResponse,
    RoadmapItemResponse,
)
from app.modules.companies.service import get_company_detail, list_companies

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


@router.get(
    "",
    response_model=PublicCompanyListResponse,
)
async def list_companies_endpoint(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_reader),
) -> PublicCompanyListResponse:
    """List active companies (public storefront)."""
    companies, total = await list_companies(
        session,
        active_only=True,
        page=page,
        per_page=per_page,
    )
    return PublicCompanyListResponse(
        items=[PublicCompanyResponse.model_validate(c) for c in companies],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{company_id}",
    response_model=PublicCompanyDetailResponse,
)
async def get_company_detail_endpoint(
    company_id: UUID,
    session: AsyncSession = Depends(get_db_reader),
) -> PublicCompanyDetailResponse:
    """Get company detail with roadmap items (public)."""
    profile, roadmap_items = await get_company_detail(company_id, session)
    response = PublicCompanyDetailResponse.model_validate(profile)
    response.roadmap = [
        RoadmapItemResponse.model_validate(item) for item in roadmap_items
    ]
    return response
