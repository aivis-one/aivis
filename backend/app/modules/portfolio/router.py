# =============================================================================
# AIVIS.ONE Backend -- Portfolio Router (Sprint 9.2)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/portfolio/me              -- all company positions
#   GET /api/v1/portfolio/me/company/{id} -- position detail + purchases
#
# AUTH:
#   Requires authenticated user (any role). Users without purchases
#   get empty positions list or 404 for company detail.
#
# COMMIT RULE (P-01):
#   Read-only endpoints use get_db_reader.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.auth.dependencies import get_current_user
from app.modules.portfolio.schemas import (
    CompanyPositionDetailResponse,
    PortfolioResponse,
)
from app.modules.portfolio.service import get_company_position, get_portfolio
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get(
    "/me",
    response_model=PortfolioResponse,
)
async def my_portfolio(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> PortfolioResponse:
    """Get detailed portfolio: positions grouped by company.

    Returns all companies where the user has active purchases.
    Companies are sorted by current value descending.
    """
    return await get_portfolio(user.id, session)


@router.get(
    "/me/company/{company_id}",
    response_model=CompanyPositionDetailResponse,
)
async def my_company_position(
    company_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanyPositionDetailResponse:
    """Get position detail for a single company with paginated purchases.

    Returns aggregate position data plus a paginated list of individual
    purchase records. Returns 404 if investor has no purchases in this company.
    """
    return await get_company_position(
        user.id,
        company_id,
        session,
        page=page,
        per_page=per_page,
    )
