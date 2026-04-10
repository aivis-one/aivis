# =============================================================================
# CBSHOME Backend -- Withdrawal Router (Sprint 6.3)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/withdrawals    -- create withdrawal request
#   GET  /api/v1/withdrawals/me -- list my withdrawals
#
# AUTH:
#   All endpoints require authenticated user with any role
#   (withdrawal is available to any User with confirmed passive balance).
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session manages it.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.users.models import User
from app.modules.withdrawals.schemas import (
    CreateWithdrawalRequest,
    WithdrawalListResponse,
    WithdrawalResponse,
)
from app.modules.withdrawals.service import create_withdrawal, get_my_withdrawals

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/withdrawals", tags=["withdrawals"])


@router.post(
    "",
    response_model=WithdrawalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_withdrawal_endpoint(
    body: CreateWithdrawalRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> WithdrawalResponse:
    """Create a withdrawal request.

    Debits passive_ledger immediately. Only one active withdrawal
    per user is allowed.
    """
    withdrawal = await create_withdrawal(user, body.amount_cents, session)
    return WithdrawalResponse.model_validate(withdrawal)


@router.get(
    "/me",
    response_model=WithdrawalListResponse,
)
async def list_my_withdrawals(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> WithdrawalListResponse:
    """List authenticated user's withdrawal history."""
    items, total = await get_my_withdrawals(
        user.id, session, page=page, per_page=per_page
    )
    return WithdrawalListResponse(
        items=[WithdrawalResponse.model_validate(w) for w in items],
        total=total,
    )
