# =============================================================================
# CBSHOME Backend -- Company Public Router (Sprint 4.1, fix Phase 4 + F4.1
#                                            + Sprint 4.5)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/companies         -- list active companies (public, ?search=)
#   GET /api/v1/companies/me      -- authenticated company's full profile (Sprint 4.5)
#   GET /api/v1/companies/{id}    -- company detail with roadmap (public)
#
# AUTH:
#   List + detail-by-id: no authentication required (public storefront).
#   /me: requires authenticated user with role=company (via
#        get_current_company_profile dependency, which raises 403
#        otherwise).
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
#
# Sprint 4.5 CHANGES:
#   - +GET /me. Frontend Phase F5 (Company UI) needs a canonical way
#     for an authenticated company user to fetch their own full profile,
#     including distribution_config (which the public /companies/{id}
#     omits for storefront privacy). Without /me the frontend has no
#     canonical path to the caller's own company_id and full settings
#     payload, since /companies/{id} requires knowing the id up-front
#     and only emits the public projection.
#   - The endpoint reuses the existing get_current_company_profile
#     dependency (already used by /api/v1/company/dashboard and
#     /api/v1/company/analytics), so role-gating and ForbiddenError
#     semantics are identical across the company-side surface.
#   - Response model is staff-side CompanyResponse, not Public*. The
#     caller IS the company; full profile (including distribution_config,
#     user_id, updated_at) is appropriate for the company's own settings
#     UI. Public projection is only for storefront visitors.
#
# ROUTE ORDERING:
#   /me must be declared BEFORE /{company_id} so FastAPI does not try
#   to parse the literal "me" as a UUID path parameter (which would
#   422 before the route even ran). Same pattern as
#   staff_router.py /roadmap/reorder vs /roadmap/{item_id}.
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
from app.modules.companies.constants import CompanyStatus
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.companies.schemas import (
    CompanyResponse,
    PublicCompanyDetailResponse,
    PublicCompanyListResponse,
    PublicCompanyResponse,
)
from app.modules.companies.service import (
    build_roadmap_item_response,
    get_company_detail,
    list_companies,
)

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


# Sprint 4.5: /me declared before /{company_id} to avoid FastAPI
# parsing "me" as a UUID. See ROUTE ORDERING note in the module
# docstring.
@router.get(
    "/me",
    response_model=CompanyResponse,
)
async def get_my_company_endpoint(
    company: CompanyProfile = Depends(get_current_company_profile),
) -> CompanyResponse:
    """Get the authenticated company user's full profile.

    Requires role=company (enforced by get_current_company_profile,
    which raises 403 ForbiddenError for any user without an attached
    CompanyProfile -- covers investor / agent / staff / platform).

    Returns the staff-side CompanyResponse including distribution_config,
    user_id, and updated_at. Use this on company-side Settings or
    Dashboard views; never call /companies/{id} for the caller's own
    company because that endpoint emits the public-projection schema
    (no distribution_config, no user_id) and 404s on non-active status.
    """
    return CompanyResponse.model_validate(company)


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

    iter 2.4 R1 §5: roadmap items now carry kind, valid_until,
    external_url, cover_url (presigned), post snippet, and linked
    product. get_company_detail batch-loads referenced posts to avoid
    N+1; build_roadmap_item_response renders each item with the
    pre-loaded post (or None when the post is unpublished/deleted).
    """
    profile, roadmap_items, posts_map = await get_company_detail(
        company_id, session
    )

    # Public endpoint: only active companies are visible.
    if profile.status != CompanyStatus.ACTIVE:
        raise NotFoundError("Company not found")

    response = PublicCompanyDetailResponse.model_validate(profile)
    response.roadmap = [
        await build_roadmap_item_response(
            item, posts_map.get(item.post_id) if item.post_id else None, session
        )
        for item in roadmap_items
    ]
    return response
