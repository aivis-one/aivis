# =============================================================================
# AIVIS.ONE Backend -- Withdrawal Staff Router (Sprint 6.3)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/staff/withdrawals              -- list all withdrawals
#   POST /api/v1/staff/withdrawals/{id}/confirm -- approve withdrawal
#   POST /api/v1/staff/withdrawals/{id}/reject  -- reject withdrawal
#
# PERMISSIONS:
#   Requires payment_review permission.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import require_staff_permission
from app.modules.users.models import User
from app.modules.withdrawals.schemas import (
    RejectWithdrawalRequest,
    StaffWithdrawalListResponse,
    WithdrawalResponse,
)
from app.modules.withdrawals.service import (
    confirm_withdrawal,
    list_all_withdrawals,
    reject_withdrawal,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/withdrawals",
    tags=["staff-withdrawals"],
)


# ---------------------------------------------------------------------------
# List all withdrawals (staff discovery)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=StaffWithdrawalListResponse,
)
async def list_withdrawals_staff(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    withdrawal_status: str | None = Query(default=None, alias="status"),
    user_id: UUID | None = Query(default=None),
    staff: User = Depends(require_staff_permission("payment_review")),
    session: AsyncSession = Depends(get_db_reader),
) -> StaffWithdrawalListResponse:
    """List all withdrawals with optional filters. Staff only.

    Filters:
      - status: withdrawal status (pending, confirmed, processing,
        completed, rejected, failed)
      - user_id: filter by specific user
    """
    withdrawals, total = await list_all_withdrawals(
        session,
        page=page,
        per_page=per_page,
        status=withdrawal_status,
        user_id=user_id,
    )

    return StaffWithdrawalListResponse(
        items=[WithdrawalResponse.model_validate(w) for w in withdrawals],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/{withdrawal_id}/confirm",
    response_model=WithdrawalResponse,
)
async def confirm_withdrawal_endpoint(
    withdrawal_id: UUID,
    staff: User = Depends(require_staff_permission("payment_review")),
    session: AsyncSession = Depends(get_db_session),
) -> WithdrawalResponse:
    """Approve a withdrawal request.

    Transitions: pending -> confirmed -> processing (MVP: immediate).
    Requires payment_review permission.
    """
    withdrawal = await confirm_withdrawal(withdrawal_id, staff, session)
    return WithdrawalResponse.model_validate(withdrawal)


@router.post(
    "/{withdrawal_id}/reject",
    response_model=WithdrawalResponse,
)
async def reject_withdrawal_endpoint(
    withdrawal_id: UUID,
    body: RejectWithdrawalRequest,
    staff: User = Depends(require_staff_permission("payment_review")),
    session: AsyncSession = Depends(get_db_session),
) -> WithdrawalResponse:
    """Reject a withdrawal request.

    Creates compensating passive_ledger entry to restore balance.
    Requires payment_review permission.
    """
    withdrawal = await reject_withdrawal(
        withdrawal_id, body.reason, staff, session
    )
    return WithdrawalResponse.model_validate(withdrawal)
