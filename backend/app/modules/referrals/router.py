# =============================================================================
# CBSHOME Backend -- Referral Router (Sprint 7.2)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/referrals/links    -- create referral link (agent only)
#   GET  /api/v1/referrals/links/me -- list my referral links (agent only)
#   GET  /api/v1/referrals/stats/me -- referral stats (agent only)
#
# AUTH:
#   All endpoints require role=agent.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session manages it.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.referrals.schemas import (
    ReferralLinkListResponse,
    ReferralLinkResponse,
    ReferralStatsResponse,
)
from app.modules.referrals.service import create_link, get_my_links, get_my_stats
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/referrals", tags=["referrals"])


def _require_agent(user: User) -> None:
    """Raise 403 if user is not an agent."""
    if user.role != UserRole.AGENT:
        raise ForbiddenError("Only agents can access referral features")


@router.post(
    "/links",
    response_model=ReferralLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_referral_link(
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> ReferralLinkResponse:
    """Create a new referral link. Agent only."""
    _require_agent(user)

    link = await create_link(user, session)
    return ReferralLinkResponse.model_validate(link)


@router.get(
    "/links/me",
    response_model=ReferralLinkListResponse,
)
async def list_my_links(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> ReferralLinkListResponse:
    """List my referral links. Agent only."""
    _require_agent(user)

    links, total = await get_my_links(
        user.id, session, page=page, per_page=per_page
    )

    return ReferralLinkListResponse(
        items=[ReferralLinkResponse.model_validate(l) for l in links],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/stats/me",
    response_model=ReferralStatsResponse,
)
async def my_referral_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> ReferralStatsResponse:
    """Get my referral stats. Agent only."""
    _require_agent(user)

    stats = await get_my_stats(user.id, session)
    return ReferralStatsResponse(**stats)
