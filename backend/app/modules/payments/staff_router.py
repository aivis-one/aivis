# =============================================================================
# AIVIS.ONE Backend -- Payment Staff Router (Sprint 5.3, G2)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/staff/payments              -- list all payments (G2)
#   POST /api/v1/staff/payments/{id}/reverse -- chargeback reversal
#
# PERMISSIONS:
#   All endpoints require payment_review permission.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import require_staff_permission
from app.modules.payments.reversal import reverse_payment
from app.modules.payments.schemas import (
    ReversePaymentRequest,
    ReversalResponse,
    StaffPaymentListResponse,
    StaffPaymentResponse,
)
from app.modules.payments.service import list_all_payments
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/payments", tags=["staff-payments"])


# ---------------------------------------------------------------------------
# List all payments (G2)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=StaffPaymentListResponse,
)
async def list_payments_staff(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    payment_status: str | None = Query(default=None, alias="status"),
    user_id: UUID | None = Query(default=None),
    staff: User = Depends(require_staff_permission("payment_review")),
    session: AsyncSession = Depends(get_db_reader),
) -> StaffPaymentListResponse:
    """List all payments with optional filters. Staff only.

    Filters:
      - status: payment status (frozen, confirmed, reversed, failed)
      - user_id: filter by specific user
    """
    payments, total = await list_all_payments(
        session,
        page=page,
        per_page=per_page,
        status=payment_status,
        user_id=user_id,
    )

    return StaffPaymentListResponse(
        items=[StaffPaymentResponse.model_validate(p) for p in payments],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# Reversal (Sprint 5.3)
# ---------------------------------------------------------------------------


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
