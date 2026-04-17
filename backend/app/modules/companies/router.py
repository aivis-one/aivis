# =============================================================================
# CBSHOME Backend -- Company Public Router (Sprint 4.1, fix Phase 4 + F4.1)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/companies       -- list active companies (public, ?search=)
#   GET /api/v1/companies/{id}  -- company detail with roadmap (public)
#
# AUTH:
#   No authentication required. Public storefront.
#
# Phase 4 FIX:
#   Detail endpoint returns 404 for non-active companies.
#   Previously returned hidden/archived companies by UUID.
#
# Sprint F4.1 CHANGES:
#   - List endpoint accepts ?search=<str>: case-insensitive ILIKE match
#     on CompanyProfile.name. Used by the Investor storefront filter
#     bottom-sheet to handle 500+ companies without shipping the whole
#     catalogue.
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
from app.modules.companies.constants import CompanyStatus
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
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_reader),
) -> PublicCompanyListResponse:
    """List active companies (public storefront).

    Optional ?search=<str> does a case-insensitive substring match on
    company name.
    """
    companies, total = await list_companies(
        session,
        active_only=True,
        search=search,
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
    """Get company detail with roadmap items (public).

    Returns 404 for non-active companies (hidden/archived).
    """
    profile, roadmap_items = await get_company_detail(company_id, session)

    # Public endpoint: only active companies are visible.
    if profile.status != CompanyStatus.ACTIVE:
        raise NotFoundError("Company not found")

    response = PublicCompanyDetailResponse.model_validate(profile)
    response.roadmap = [
        RoadmapItemResponse.model_validate(item) for item in roadmap_items
    ]
    return response
