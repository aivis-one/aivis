# =============================================================================
# CBSHOME Backend -- Company Auth Router (Sprint 4.5; trimmed in iter 2.4)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/companies/me  -- authenticated company's full profile
#
# iter 2.4 MIGRATION:
#   GET /api/v1/companies              (list)   moved to companies/public_router.py
#   GET /api/v1/companies/{company_id} (detail) moved to companies/public_router.py
#
#   See companies/public_router.py for rationale. /me stays here because
#   it is the only auth-gated endpoint under this prefix and the public
#   router lives under a different prefix entirely.
#
# AUTH:
#   /me requires authenticated user with role=company (via
#   get_current_company_profile dependency, which raises 403
#   ForbiddenError for any user without a CompanyProfile).
#
# Sprint 4.5 RATIONALE:
#   Frontend Phase F5 (Company UI) needs a canonical way for a
#   company-role caller to fetch its own full profile, including
#   distribution_config (which PublicCompanyDetailResponse omits for
#   storefront privacy) and respecting non-active status (which the
#   public detail 404s on).
# =============================================================================

from fastapi import APIRouter, Depends

from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.companies.schemas import CompanyResponse

router = APIRouter(prefix="/api/v1/companies", tags=["companies"])


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
    Dashboard views; never call the public detail endpoint for the
    caller's own company because that endpoint emits the public
    projection (no distribution_config, no user_id) and 404s on
    non-active status.
    """
    return CompanyResponse.model_validate(company)
