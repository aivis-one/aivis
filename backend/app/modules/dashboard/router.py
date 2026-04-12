# =============================================================================
# CBSHOME Backend -- Dashboard Router (Sprint 9.2)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/dashboard/summary -- aggregated portfolio widget
#
# AUTH:
#   Requires authenticated user (any role). Users without purchases
#   get zeroed-out response.
#
# COMMIT RULE (P-01):
#   Read-only endpoint uses get_db_reader.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.auth.dependencies import get_current_user
from app.modules.dashboard.schemas import DashboardSummaryResponse
from app.modules.dashboard.service import get_dashboard_summary
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummaryResponse,
)
async def dashboard_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> DashboardSummaryResponse:
    """Aggregated data for the investor main screen.

    Returns ledger balances, portfolio totals, and per-company breakdown.
    Users without purchases get zeroed-out values with empty companies list.
    """
    return await get_dashboard_summary(user.id, session)
