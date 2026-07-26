# =============================================================================
# AIVIS.ONE Backend -- Referral Router (Sprint 7.2, Task 1 Block D, Task 2b)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/referrals/links       -- create referral link (agent only)
#   GET  /api/v1/referrals/links/me    -- list my referral links (agent only)
#   GET  /api/v1/referrals/stats/me    -- referral stats (agent only)
#   GET  /api/v1/referrals/downline/me -- my downline by level (agent only)
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
#   Task 2b: downline assembly + PII MASKING also happen here -- the
#   service returns raw User rows, the router applies
#   _mask_display_name uniformly to both collections. The wire never
#   carries email, phone or KYC status (decision #5).
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
    DownlineInvestorEntry,
    DownlineSubAgentEntry,
    ReferralDownlineResponse,
    ReferralLinkListResponse,
    ReferralLinkResponse,
    ReferralStatsResponse,
)
from app.modules.referrals.service import (
    create_link,
    get_downline,
    get_my_links,
    get_my_stats,
)
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/referrals", tags=["referrals"])


def _require_agent(user: User) -> None:
    """Raise 403 if user is not an agent."""
    if user.role != UserRole.AGENT:
        raise ForbiddenError("Only agents can access referral features")


def _mask_display_name(user: User) -> str:
    """Masked display name for downline entries (decision #5).

    Uniform for ALL levels -- never the full identity, never email,
    phone or KYC. Resolution order:
      1. profile first_name + last-name initial ("Ivan P.");
      2. telegram first_name + last-name initial;
      3. masked email local-part, first two chars ("iv***");
      4. role-generic fallback ("Investor" / "Agent").
    """
    profile = user.profile or {}
    tg = (user.credentials or {}).get("telegram", {})

    for source in (profile, tg):
        first = (source.get("first_name") or "").strip()
        last = (source.get("last_name") or "").strip()
        if first:
            return f"{first} {last[0]}." if last else first

    email = user.email
    if email:
        local = email.split("@", 1)[0]
        return f"{local[:2]}***"

    return "Agent" if user.role == UserRole.AGENT else "Investor"


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


@router.get(
    "/downline/me",
    response_model=ReferralDownlineResponse,
)
async def my_downline(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> ReferralDownlineResponse:
    """My downline by level (Task 2b). Agent only.

    Two collections (decision #1): investors L1-L3 (commission-mirror
    levels) and sub-agents at agent-hop depth 1-3. Assembly and PII
    masking happen here (Pattern 6); the service returns raw rows.
    No pagination in v1 (decision #7) -- depth-3 bounds the size.
    """
    _require_agent(user)

    investors, sub_agents = await get_downline(user.id, session)

    return ReferralDownlineResponse(
        investors=[
            DownlineInvestorEntry(
                user_id=u.id,
                display_name=_mask_display_name(u),
                level=level,
                registered_at=u.created_at,
                purchase_volume_cents=volume,
            )
            for u, level, volume in investors
        ],
        sub_agents=[
            DownlineSubAgentEntry(
                user_id=a.id,
                display_name=_mask_display_name(a),
                level=level,
                registered_at=a.created_at,
                recruited_investor_count=recruited,
                direct_volume_cents=direct_vol,
                own_purchase_volume_cents=own_vol,
            )
            for a, level, recruited, direct_vol, own_vol in sub_agents
        ],
    )
