# =============================================================================
# AIVIS.ONE Backend -- Company Auth Router (Sprint 4.5; trimmed in iter 2.4;
#                                           TASK-30 self-service PATCH added)
# =============================================================================
#
# ENDPOINTS:
#   GET   /api/v1/companies/me  -- authenticated company's full profile
#   PATCH /api/v1/companies/me  -- TASK-30 ruling 10/12, TIME-BOXED
#                                   EXCEPTION added by TASK-39 item 6:
#                                   project self-service partial update,
#                                   restricted to the project-editable
#                                   field set (description/logo_url/
#                                   cover_url/promo_video_url/
#                                   presentation_url/name/
#                                   price_per_unit_cents/total_supply/
#                                   shares_per_option + status
#                                   ACTIVE->HIDDEN only). distribution_config
#                                   and the OptionPool stay admin-only. No
#                                   company_id path parameter exists on
#                                   this route -- the row is entirely
#                                   determined by get_current_company_profile's
#                                   lookup on the caller's own user_id, so
#                                   there is no way to even address another
#                                   company's row through this endpoint.
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
#   /me (both verbs) requires authenticated user with role=company (via
#   get_current_company_profile dependency, which raises 403
#   ForbiddenError for any user without a CompanyProfile).
#
# Sprint 4.5 RATIONALE:
#   Frontend Phase F5 (Company UI) needs a canonical way for a
#   company-role caller to fetch its own full profile, including
#   distribution_config (which PublicCompanyDetailResponse omits for
#   storefront privacy) and respecting non-active status (which the
#   public detail 404s on).
#
# TASK-30 PATCH /me SESSION NOTE:
#   get_current_company_profile is wired to get_db_reader (a rollback-only
#   session; see companies/dependencies.py) -- correct for the GET here
#   and for company_dashboard's two GET endpoints, its only other callers.
#   PATCH needs a writer session (get_db_session) to commit. Rather than
#   mutating the reader-bound `company` object handed back by the
#   dependency -- which would attach the change to the wrong Session and
#   never reach the writer session's flush -- the endpoint below passes
#   only `company.id` into update_own_company(), which re-loads the row
#   via get_company() against the writer session it was actually given.
#   This mirrors update_company()'s existing (company_id, session) shape.
# =============================================================================

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.companies.schemas import CompanyResponse, UpdateOwnCompanyRequest
from app.modules.companies.service import update_own_company

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


@router.patch(
    "/me",
    response_model=CompanyResponse,
)
async def update_my_company_endpoint(
    body: UpdateOwnCompanyRequest,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Partial self-update of the authenticated company's own profile.

    TASK-30 ownership line (§4): "the project describes; the admin owns
    and prices." TASK-39 item 6 SUPERSEDES that line IN PART, by
    explicit owner ruling (2026-08): because every company on the
    platform today is the owner's own project rather than a third party,
    UpdateOwnCompanyRequest now ALSO carries name, price_per_unit_cents,
    total_supply, and shares_per_option, alongside the original
    description/logo_url/cover_url/promo_video_url/presentation_url/
    status set. This is TIME-BOXED, not a repeal -- it holds only while
    every company remains the owner's own, and admin-side price/volume
    validation must land before the first non-owner company is
    onboarded (see TASK-39 item 6, owner ruling 2026-08-29). A price
    change here is NOT a plain field write: update_own_company() routes
    it through cascade_price() via the same `_apply_price_change` helper
    the staff price endpoint uses, so it cascades to products,
    soft-deletes installment templates, and records price history +
    audit exactly like the staff path (see companies/service.py).

    distribution_config and the OptionPool are UNCHANGED by this
    supersession -- they and any other field not listed above are not
    representable in the request body at all (extra="forbid"), so a
    request carrying any of them 422s at the schema boundary before this
    function body ever runs; there is nothing to strip. The publication
    asymmetry (a project may go ACTIVE->HIDDEN; only staff may publish
    or archive) is also unchanged -- see the status paragraph below.

    Requires role=company, same as GET /me. No company_id path parameter:
    the row updated is entirely determined by get_current_company_profile's
    lookup on the caller's own user_id (companies/dependencies.py) --
    isolation here is structural (there is no id in the URL to attack),
    not a runtime ownership check.

    `status`, when provided, must be the single legal project-initiated
    transition ACTIVE -> HIDDEN (ruling 12: the project may withdraw
    itself; only a staff admin may publish HIDDEN -> ACTIVE or set
    ARCHIVED, via PATCH /staff/companies/{id}). Any other requested
    status is rejected by update_own_company() with BadRequestError (400).

    See the TASK-30 PATCH /me SESSION NOTE above the router prefix for
    why only `company.id` (not the `company` object itself) is passed
    into the service call.
    """
    updated = await update_own_company(company.id, body, session)
    return CompanyResponse.model_validate(updated)
