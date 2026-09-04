# =============================================================================
# AIVIS.ONE Backend -- KYC Router (Sprint 2.1, H10)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/kyc/submit   -- pay the fee and open a verification
#                                session (auth required)
#   GET  /api/v1/kyc/status   -- current status, fee, and balance
#                                (auth required)
#
# BOTH ARE IN FRONT OF THE KYC GATE (kyc/gate.py's exempt list). A gate
# standing in front of the only door through it would lock every new
# investor out of the product permanently -- the same self-lock that
# put the deposit endpoints on that list.
#
# WHAT IS GONE, AND IT IS NOT COMING BACK IN THIS SHAPE (H10 P-44):
#   POST /webhook  -- the stub provider receiver. It authenticated by
#                     comparing a shared secret with hmac.compare_digest
#                     and no emptiness check, against a setting that
#                     defaulted to the empty string: with the secret
#                     unset and the header absent, the comparison was
#                     "" against "", which is True, and the request
#                     then approved whatever user id its body named.
#                     Removed rather than repaired -- the verification
#                     provider that replaces it signs its callbacks.
#   POST /advance  -- an onboarding-unstick hotfix for a step that no
#                     longer exists.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
#
# SESSION NOTE:
#   GET /status uses get_current_user (read session) + get_db_reader.
#   FastAPI caches Depends within a request, so both share the same
#   read-only session instance.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.kyc.schemas import KYCStatusResponse, KYCSubmitResponse
from app.modules.kyc.service import get_kyc_status, submit_kyc
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/kyc", tags=["kyc"])


@router.post(
    "/submit",
    response_model=KYCSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    # R49: staff in avatar mode must not submit KYC for the user. The
    # guard matters more since H10 than it did before: submitting now
    # spends the user's money.
    dependencies=[Depends(forbid_avatar("modify_kyc"))],
)
async def kyc_submit(
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> KYCSubmitResponse:
    """Open a verification session, charging the fee up front.

    402 from the gate means "not verified"; this endpoint answers 400
    with insufficient_balance when the account cannot cover the fee,
    and 409 when a session is already open and awaiting a decision.
    """
    application = await submit_kyc(user, session)
    return KYCSubmitResponse.model_validate(application)


@router.get(
    "/status",
    response_model=KYCStatusResponse,
)
async def kyc_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> KYCStatusResponse:
    """Current KYC status, what a session costs, and what is available.

    get_current_user and get_db_reader share the same read-only session
    (FastAPI Depends caching within a request).
    """
    return await get_kyc_status(user, session)
