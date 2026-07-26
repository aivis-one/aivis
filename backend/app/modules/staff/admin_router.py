# =============================================================================
# AIVIS.ONE Backend -- Admin Router (Sprint 3.3, G5 fix)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/staff/dashboard/stats  -- platform statistics (any staff)
#   GET  /api/v1/staff/kyc/queue        -- pending KYC applications (kyc_approve)
#   POST /api/v1/staff/kyc/{id}/approve -- approve KYC (kyc_approve)
#   POST /api/v1/staff/kyc/{id}/reject  -- reject KYC (kyc_approve, optional reason)
#
# AUTH:
#   Dashboard: any staff (get_current_staff).
#   KYC: requires kyc_approve permission (require_staff_permission).
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_staff, require_staff_permission
from app.modules.staff.admin_schemas import (
    DashboardStatsResponse,
    KYCQueueItem,
    KYCRejectRequest,
)
from app.modules.staff.admin_service import (
    dashboard_stats,
    kyc_approve,
    kyc_queue,
    kyc_reject,
)
from app.modules.users.models import User

logger = structlog.get_logger()

# Two sub-routers under /api/v1/staff.
dashboard_router = APIRouter(
    prefix="/api/v1/staff/dashboard",
    tags=["staff-dashboard"],
)
kyc_admin_router = APIRouter(
    prefix="/api/v1/staff/kyc",
    tags=["staff-kyc"],
)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@dashboard_router.get(
    "/stats",
    response_model=DashboardStatsResponse,
)
async def get_dashboard_stats(
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_reader),
) -> DashboardStatsResponse:
    """Platform-wide statistics. Any staff can view."""
    return await dashboard_stats(session)


# ---------------------------------------------------------------------------
# KYC queue
# ---------------------------------------------------------------------------


@kyc_admin_router.get(
    "/queue",
    response_model=list[KYCQueueItem],
)
async def get_kyc_queue(
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_reader),
) -> list[KYCQueueItem]:
    """List pending KYC applications. Requires kyc_approve permission."""
    return await kyc_queue(session)


@kyc_admin_router.post(
    "/{application_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def kyc_approve_endpoint(
    application_id: UUID,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Approve a KYC application. Requires kyc_approve permission."""
    await kyc_approve(application_id, staff, session)


@kyc_admin_router.post(
    "/{application_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def kyc_reject_endpoint(
    application_id: UUID,
    body: KYCRejectRequest,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Reject a KYC application. Requires kyc_approve permission."""
    await kyc_reject(application_id, staff, session, reason=body.reason)
