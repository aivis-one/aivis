# =============================================================================
# CBSHOME Backend -- KYC Router (Sprint 2.1)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/kyc/submit   -- Submit KYC application (auth required)
#   GET  /api/v1/kyc/status   -- Get current KYC status (auth required)
#   POST /api/v1/kyc/webhook  -- SumSub webhook handler (stub, secret required)
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
# =============================================================================

import hmac

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import UnauthorizedError
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.kyc.schemas import (
    KYCStatusResponse,
    KYCSubmitResponse,
    KYCWebhookRequest,
)
from app.modules.kyc.service import get_kyc_status, process_webhook, submit_kyc
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/kyc", tags=["kyc"])


@router.post(
    "/submit",
    response_model=KYCSubmitResponse,
    status_code=status.HTTP_201_CREATED,
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
