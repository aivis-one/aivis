# =============================================================================
# CBSHOME Backend -- Referral Router (Sprint 7.2, extended Task 1 Block D)
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
# RESPONSE ASSEMBLY (Pattern 6, Task 1 Block D):
#   ReferralLinkResponse now carries per-link counters
#   (click_count / registration_count / purchase_count) plus is_active.
#   get_my_links returns (link, registration_count, purchase_count)
#   tuples; the router builds the response explicitly. A freshly
#   created link has zero registrations/purchases by definition, so
#   the create endpoint hardcodes 0/0 instead of querying.
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
from app.modules.referrals.models import ReferralLink
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


def _link_response(
    link: ReferralLink,
    registration_count: int,
    purchase_count: int,
) -> ReferralLinkResponse:
    """Assemble ReferralLinkResponse from a link row + its aggregates."""
    return ReferralLinkResponse(
        id=link.id,
        agent_id=link.agent_id,
        code=link.code,
        is_active=link.is_active,
        click_count=link.click_count,
        registration_count=registration_count,
        purchase_count=purchase_count,
        created_at=link.created_at,
    )


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
    # A brand-new link has no registrations or purchases yet.
    return _link_response(link, registration_count=0, purchase_count=0)


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
    """List my referral links with per-link counters. Agent only."""
    _require_agent(user)

    enriched, total = await get_my_links(
        user.id, session, page=page, per_page=per_page
    )

    return ReferralLinkListResponse(
        items=[
            _link_response(link, reg_count, purch_count)
            for link, reg_count, purch_count in enriched
        ],
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
