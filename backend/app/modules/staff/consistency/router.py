# =============================================================================
# AIVIS.ONE Backend -- Consistency Router (Sprint 6.4)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/staff/consistency -- run all semaphores
#
# PERMISSIONS:
#   Requires financial_operations permission.
#
# COMMIT RULE (P-01):
#   Read-only endpoint. Uses get_db_reader for replica routing.
#   Audit writes (for failures) go through the same session --
#   uses get_db_session to allow audit writes.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.staff.consistency.schemas import ConsistencyResponse
from app.modules.staff.consistency.service import run_all
from app.modules.auth.dependencies import require_staff_permission
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/consistency",
    tags=["staff-consistency"],
)


@router.get(
    "",
    response_model=ConsistencyResponse,
)
async def check_consistency(
    staff: User = Depends(require_staff_permission("financial_operations")),
    session: AsyncSession = Depends(get_db_session),
) -> ConsistencyResponse:
    """Run all consistency semaphores and return results.

    Failures are logged to audit_log and structlog.
    Requires financial_operations permission.
    """
    results = await run_all(session, staff_id=staff.id)

    passed = sum(1 for r in results if r.status == "pass")
    failed = len(results) - passed

    return ConsistencyResponse(
        overall_status="pass" if failed == 0 else "fail",
        total=len(results),
        passed=passed,
        failed=failed,
        results=results,
    )
