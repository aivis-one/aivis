# =============================================================================
# CBSHOME Backend -- Payment Staff Router (Sprint 5.3)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/staff/payments/{id}/reverse -- chargeback reversal
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
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import require_staff_permission
from app.modules.payments.reversal import reverse_payment
from app.modules.payments.schemas import ReversePaymentRequest, ReversalResponse
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/payments", tags=["staff-payments"])


@router.post(
    "/{payment_id}/reverse",
    response_model=ReversalResponse,
    status_code=status.HTTP_200_OK,
)
async def reverse_payment_endpoint(
    payment_id: UUID,
    body: ReversePaymentRequest,
    staff: User = Depends(require_staff_permission("payment_review")),
    session: AsyncSession = Depends(get_db_session),
) -> ReversalResponse:
    """Reverse a payment (chargeback).

    Creates mirror ledger entries with negative amounts and marks
    originals as reversed. Payment transitions to reversed status.

    Requires payment_review permission.
    """
    result = await reverse_payment(
        payment_id,
        staff.id,
        session,
        reason=body.reason,
    )
    return ReversalResponse.model_validate(result)
