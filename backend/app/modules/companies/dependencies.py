# =============================================================================
# CBSHOME Backend -- Company FastAPI Dependencies (Sprint 4.3 / B5)
# =============================================================================
#
# Dependencies for FastAPI routes that operate on the company that the
# authenticated user owns. Lives in companies/ (rather than
# company_dashboard/) so future company-side modules (settings, payouts,
# referrals overview) can reuse the same loader without depending on the
# dashboard module.
#
# get_current_company_profile():
#   Loads the CompanyProfile linked to the authenticated user. Raises
#   ForbiddenError when the user has no associated profile -- which
#   covers both "investor calling a /company/* endpoint" and "staff
#   calling /company/* without an avatar session". The error returned
#   matches the user-facing meaning ("you are not a company"), even if
#   the technical reason is "no row in company_profiles for your user_id".
# =============================================================================

import structlog
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import get_current_user
from app.modules.companies.models import CompanyProfile
from app.modules.users.models import User

logger = structlog.get_logger()


async def get_current_company_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanyProfile:
    """Load the CompanyProfile for the authenticated company user.

    Used by /api/v1/company/* routes that need to operate on the
    caller's own company. Read-only; the dependency uses get_db_reader.

    Raises:
        ForbiddenError: If the authenticated user has no CompanyProfile.
    """
    stmt = select(CompanyProfile).where(CompanyProfile.user_id == user.id)
    result = await session.execute(stmt)
    company = result.scalar_one_or_none()

    if company is None:
        # 403, not 404. The user is authenticated -- they're just not
        # authorised to use a company-only endpoint.
        raise ForbiddenError("User is not linked to a company")

    return company
