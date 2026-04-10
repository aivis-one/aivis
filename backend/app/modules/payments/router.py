# =============================================================================
# CBSHOME Backend -- Payment Router (Sprint 5.2, fix Sprint 6.1)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/payments/crypto-address       -- get/create deposit address
#   GET  /api/v1/payments/history              -- payment history (investor)
#
# AUTH:
#   All endpoints require authentication.
#
# Sprint 6.1 FIX (TD-029):
#   create_crypto_address uses get_current_user_write (not get_current_user)
#   so auth dependency and endpoint share the same write session.
#   FastAPI caches Depends within a request -- one DB connection, no merge.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.payments.schemas import (
    CreateAddressRequest,
    DepositAddressResponse,
    PaymentHistoryResponse,
    PaymentResponse,
)
from app.modules.payments.service import (
    get_or_create_deposit_address,
    list_payments,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.post(
    "/crypto-address",
    response_model=DepositAddressResponse,
)
async def create_crypto_address(
    body: CreateAddressRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> DepositAddressResponse:
    """Get or create a crypto deposit address for the authenticated user.

    Idempotent: returns existing address if one exists for this network.
    Uses write session (TD-029 fix: single session shared with auth).
    """
    deposit = await get_or_create_deposit_address(user.id, body.network, session)
    return DepositAddressResponse(
        address=deposit.address,
        network=deposit.network,
        user_id=deposit.user_id,
    )


@router.get(
    "/history",
    response_model=PaymentHistoryResponse,
)
async def get_payment_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> PaymentHistoryResponse:
    """List payment history for the authenticated user."""
    payments, total = await list_payments(
        user.id,
        session,
        page=page,
        per_page=per_page,
    )
    return PaymentHistoryResponse(
        items=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
        page=page,
        per_page=per_page,
    )
