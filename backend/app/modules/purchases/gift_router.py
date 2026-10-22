# =============================================================================
# AIVIS.ONE Backend -- Gift Router
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/purchases/gifts/pending          -- my gifts waiting for me
#   POST /api/v1/purchases/{purchase_id}/accept-gift -- accept one: the parts
#                                                       are credited
#
# The staff side (the grant) is in purchases/staff_router.py.
#
# AUTH:
#   Any authenticated investor-side user; a gift is addressed by purchase id
#   and only its recipient finds it (someone else's id answers 404).
#   Accepting is blocked in avatar mode: it is an acquisition of ownership,
#   guarded under the existing "create_purchase" operation name.
#
# KYC GATE:
#   POST accept-gift is open by decision (tests/test_kyc_gate.py): the
#   service checks KYC itself, at the grant (grant_gift) and again at the
#   acceptance (accept_gift, code kyc_required).
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.purchases.gift_service import accept_gift, list_pending_gifts
from app.modules.purchases.schemas import GiftListResponse, PurchaseResponse
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1/purchases", tags=["purchase-gifts"])


@router.get("/gifts/pending", response_model=GiftListResponse)
async def my_pending_gifts(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> GiftListResponse:
    """Gifts granted to the caller that wait for acceptance."""
    gifts = await list_pending_gifts(user.id, session)
    return GiftListResponse(
        items=[PurchaseResponse.model_validate(g) for g in gifts],
        total=len(gifts),
    )


@router.post(
    "/{purchase_id}/accept-gift",
    response_model=PurchaseResponse,
    dependencies=[Depends(forbid_avatar("create_purchase"))],
)
async def accept_gift_endpoint(
    purchase_id: UUID,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> PurchaseResponse:
    """Accept a pending gift: the parts are credited and the gift becomes
    an active holding."""
    purchase = await accept_gift(purchase_id, user, session)
    return PurchaseResponse.model_validate(purchase)
