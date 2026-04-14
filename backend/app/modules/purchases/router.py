# =============================================================================
# CBSHOME Backend -- Purchase Router (Sprint 6.1, G3 fix)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/products/{id}/purchase -- instant purchase
#
# AUTH:
#   Requires authenticated buyer (role=investor or role=agent).
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session manages it.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import get_current_user_write
from app.modules.purchases.schemas import (
    CreatePurchaseRequest,
    PurchaseResponse,
)
from app.modules.purchases.service import execute_purchase
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/products", tags=["purchases"])

# Roles allowed to purchase products (investors and agents).
_BUYER_ROLES = {UserRole.INVESTOR, UserRole.AGENT}


@router.post(
    "/{product_id}/purchase",
    response_model=list[PurchaseResponse],
    status_code=status.HTTP_201_CREATED,
)
async def purchase_product(
    product_id: UUID,
    body: CreatePurchaseRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> list[PurchaseResponse]:
    """Purchase a product (instant buy).

    Returns list of Purchase records: one for the sale, plus any
    gift allocations triggered by purchase_config.bonuses[].

    Requires: authenticated investor or agent.
    """
    if user.role not in _BUYER_ROLES:
        raise ForbiddenError("Only investors and agents can purchase products")

    purchases = await execute_purchase(
        product_id=product_id,
        investor=user,
        session=session,
        referral_link_id=body.referral_link_id,
    )

    return [PurchaseResponse.model_validate(p) for p in purchases]
