# =============================================================================
# AIVIS.ONE Backend -- KYC Router (Sprint 2.1, iter 2.7 onboarding-advance hotfix)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/kyc/submit   -- Submit KYC application (auth required)
#   GET  /api/v1/kyc/status   -- Get current KYC status (auth required)
#   POST /api/v1/kyc/advance  -- Advance onboarding past KYC if stuck
#                                (auth required, idempotent) [iter 2.7]
#   POST /api/v1/kyc/webhook  -- SumSub webhook handler (stub,
#                                secret required)
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
#
# SESSION NOTE:
#   GET /status uses get_current_user (read session) + get_db_reader.
#   FastAPI caches Depends within a request, so both share the same
#   read-only session instance.
#
# WEBHOOK SECURITY:
#   Stub webhook requires X-Webhook-Secret header matching
#   settings.kyc_webhook_secret. In production, this will be replaced
#   with SumSub HMAC signature validation.
#
# iter 2.7 ADVANCE ENDPOINT:
#   POST /advance exists for the re-entry case where a user's
#   kyc_status is already submitted/approved/rejected but
#   onboarding_step is still ROLE_SELECTED. The frontend's
#   /onboarding/kyc Continue button (approved or rejected branch)
#   calls /advance, then fetchMe(), then navigates to root --
#   guaranteeing the onboarding guard sees a step past KYC and
#   forwards to the next page (or the dashboard).
#
#   The endpoint is intentionally idempotent (delegates to the
#   identically-named service helper). Calling it on a happy-path
#   user is a no-op and returns 204 unchanged.
# =============================================================================

import hmac

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import UnauthorizedError
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.kyc.schemas import (
    KYCStatusResponse,
    KYCSubmitResponse,
    KYCWebhookRequest,
)
from app.modules.kyc.service import (
    advance_onboarding_after_kyc,
    get_kyc_status,
    process_webhook,
    submit_kyc,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/kyc", tags=["kyc"])


@router.post(
    "/submit",
    response_model=KYCSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    # R49: staff in avatar mode must not submit KYC for the user.
    # POST /advance is intentionally NOT guarded (boss decision): it is
    # an idempotent onboarding unstick helper that changes no KYC data,
    # and staff legitimately use it via avatar to unstick users.
    dependencies=[Depends(forbid_avatar("modify_kyc"))],
)
async def kyc_submit(
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> KYCSubmitResponse:
    """Submit a new KYC application.

    Creates a KYCApplication and sets User.kyc_status to submitted.
    Rejects if user already has a pending application.
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
    """Get the current KYC status for the authenticated user.

    get_current_user and get_db_reader share the same read-only session
    (FastAPI Depends caching within a request).
    """
    return await get_kyc_status(user, session)


@router.post(
    "/advance",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def kyc_advance(
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Advance onboarding past the KYC step if the user is stuck on it.

    Idempotent. Returns 204 in all cases (including no-op). Used by
    the frontend's /onboarding/kyc Continue button to unstick users
    whose kyc_status is already submitted/approved/rejected but
    whose onboarding_step is still ROLE_SELECTED -- a state that
    can be reached via DB seeds, manual edits, or any path that
    sets the cache without going through submit_kyc().

    Calling this on a user already past the KYC step is a no-op
    (see advance_onboarding_after_kyc docstring for the guard
    rules). The endpoint does not require kyc_status=approved --
    submitted and rejected are both legitimate states from which
    the user should be able to proceed (rejected users follow the
    retry button, but the advancement itself is one-way and
    idempotent).
    """
    await advance_onboarding_after_kyc(user, session)


@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
)
async def kyc_webhook(
    body: KYCWebhookRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """SumSub webhook handler (stub).

    Requires X-Webhook-Secret header matching settings.kyc_webhook_secret.
    In production, this will be replaced with SumSub HMAC signature
    validation. No user authentication -- webhooks come from external provider.
    """
    # Timing-safe comparison to prevent secret enumeration via side-channel.
    webhook_secret = request.headers.get("X-Webhook-Secret", "")
    if not hmac.compare_digest(webhook_secret, settings.kyc_webhook_secret):
        logger.warning(
            "kyc_webhook_unauthorized",
            user_id=str(body.user_id),
        )
        raise UnauthorizedError("Invalid webhook secret")

    await process_webhook(
        user_id=body.user_id,
        new_status=body.status,
        session=session,
    )

    logger.info(
        "kyc_webhook_received",
        user_id=str(body.user_id),
        status=body.status,
    )

    return {"status": "ok"}
