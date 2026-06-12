# =============================================================================
# CBSHOME Backend -- Commission Router (Sprint 7.3, Task 2b Block C)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/agent/leaderboard         -- top agents (agent only)
#   GET /api/v1/agent/commissions/me      -- commission history (agent only)
#   GET /api/v1/agent/commissions/summary -- month-to-date commission
#                                            aggregate (agent only, Task 2b)
#
# AUTH:
#   All endpoints require role=agent.
#
# COMMIT RULE (P-01):
#   Read-only endpoints use get_db_reader.
# =============================================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import get_current_user
from app.modules.commissions.schemas import (
    CommissionListResponse,
    CommissionSummaryResponse,
    LeaderboardResponse,
)
from app.modules.commissions.service import (
    get_commission_month_to_date,
    get_leaderboard,
    get_my_commissions,
)
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def _require_agent(user: User) -> None:
    """Raise 403 if user is not an agent."""
    if user.role != UserRole.AGENT:
        raise ForbiddenError("Only agents can access this feature")


@router.get(
    "/leaderboard",
    response_model=LeaderboardResponse,
)
async def leaderboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> LeaderboardResponse:
    """Get current agent leaderboard. Agent only."""
    _require_agent(user)
    return await get_leaderboard(user.id, session)


@router.get(
    "/commissions/me",
    response_model=CommissionListResponse,
)
async def my_commissions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> CommissionListResponse:
    """Get my commission and volume bonus history. Agent only."""
    _require_agent(user)
    return await get_my_commissions(user.id, session, limit=limit, offset=offset)


@router.get(
    "/commissions/summary",
    response_model=CommissionSummaryResponse,
)
async def my_commission_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> CommissionSummaryResponse:
    """Month-to-date commission aggregate. Agent only (Task 2b Block C).

    Server-side replacement for the dashboard's client-side sum over
    the first 100 history entries (TD-COMMISSION-MONTH-AGG). Current
    UTC month, frozen+confirmed, reversed excluded.
    """
    _require_agent(user)
    month_to_date = await get_commission_month_to_date(user.id, session)
    return CommissionSummaryResponse(month_to_date_cents=month_to_date)
