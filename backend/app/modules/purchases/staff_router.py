# =============================================================================
# AIVIS.ONE Backend -- Purchase Staff Router (R-2.2 Block B)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/staff/purchases/{id}/reverse -- manual purchase chargeback
#   POST /api/v1/staff/purchases/gifts        -- grant gift parts
#   POST /api/v1/staff/purchases/gifts/{id}/cancel -- cancel a gift not yet
#                                                     accepted
#
# PERMISSIONS:
#   reverse: payment_review -- the same permission that gates payment reversal:
#   both operations move money via mirror entries, one reviewer role.
#   gifts: financial_operations.
#
# Lives in purchases/ (not staff/) -- same modularity rule as
# payments/staff_router.py (P5-22): a future service split takes the
# whole module.
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
from app.modules.purchases.gift_service import cancel_gift, grant_gift
from app.modules.purchases.reversal import reverse_purchase
from app.modules.purchases.schemas import (
    PurchaseReversalResponse,
    PurchaseResponse,
    StaffGrantGiftRequest,
    StaffReversePurchaseRequest,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/purchases", tags=["staff-purchases"])


@router.post(
    "/gifts",
    response_model=PurchaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_gift_endpoint(
    body: StaffGrantGiftRequest,
    staff: User = Depends(require_staff_permission("financial_operations")),
    session: AsyncSession = Depends(get_db_session),
) -> PurchaseResponse:
    """Grant gift parts to a user who passed KYC.

    Stores the gift as a purchase in 'pending_acceptance': nothing is
    credited and no pool units are used until the recipient accepts it
    (POST /api/v1/purchases/{id}/accept-gift).

    Requires financial_operations: a gift gives away parts of a project,
    the same tier as shaping an offer (products' installments).
    """
    purchase = await grant_gift(
        staff=staff,
        user_id=body.user_id,
        product_id=body.product_id,
        units=body.units,
        session=session,
    )
    return PurchaseResponse.model_validate(purchase)


@router.post(
    "/gifts/{purchase_id}/cancel",
    response_model=PurchaseResponse,
)
async def cancel_gift_endpoint(
    purchase_id: UUID,
    staff: User = Depends(require_staff_permission("financial_operations")),
    session: AsyncSession = Depends(get_db_session),
) -> PurchaseResponse:
    """Cancel a staff gift the recipient has not accepted yet.

    Closes the row (status cancelled) with no ledger entry and no credit;
    an accepted gift is reversed through the purchase reversal instead.

    Requires financial_operations, like the grant.
    """
    purchase = await cancel_gift(purchase_id, staff, session)
    return PurchaseResponse.model_validate(purchase)


@router.post(
    "/{purchase_id}/reverse",
    response_model=PurchaseReversalResponse,
    status_code=status.HTTP_200_OK,
)
async def reverse_purchase_endpoint(
    purchase_id: UUID,
    body: StaffReversePurchaseRequest,
    staff: User = Depends(require_staff_permission("payment_review")),
    session: AsyncSession = Depends(get_db_session),
) -> PurchaseReversalResponse:
    """Manually reverse a purchase (staff chargeback, R-2.2 Block B).

    Unwinds the purchase's full money graph by reason (investor
    refund + platform/company/agent clawback), flips the Purchase to
    REVERSED; units return to the pool. Works regardless of how the
    purchase was funded (confirmed or frozen) -- the funding Payment
    itself is not touched.

    Requires payment_review permission.
    """
    result = await reverse_purchase(
        purchase_id,
        staff.id,
        session,
        reason=body.reason,
    )
    return PurchaseReversalResponse.model_validate(result)
