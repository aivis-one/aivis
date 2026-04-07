# =============================================================================
# CBSHOME Backend -- Payment Webhook Router (Sprint 5.2)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/payments/crypto/webhook  -- blockchain webhook
#
# AUTH:
#   Shared secret via X-Webhook-Secret header.
#   Uses hmac.compare_digest() for timing-safe comparison (TD-SEC1).
#
# FLOW:
#   1. Validate webhook secret (timing-safe)
#   2. Parse body as CryptoWebhookRequest
#   3. Delegate to service.process_crypto_webhook()
#   4. Return payment id + status
#
# COMMIT RULE (P-01):
#   Router never commits. get_db_session commits after yield.
# =============================================================================

import hmac

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.exceptions import UnauthorizedError
from app.modules.payments.schemas import CryptoWebhookRequest
from app.modules.payments.service import process_crypto_webhook

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/payments/crypto", tags=["payments-webhook"])


def _verify_webhook_secret(request: Request) -> None:
    """Validate X-Webhook-Secret header using timing-safe comparison.

    Raises:
        UnauthorizedError: If secret is missing or does not match.
    """
    provided = request.headers.get("X-Webhook-Secret", "")

    if not hmac.compare_digest(provided, settings.crypto_webhook_secret):
        raise UnauthorizedError("Invalid webhook secret")


@router.post("/webhook")
async def crypto_webhook(
    body: CryptoWebhookRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Process incoming crypto payment webhook.

    Validates shared secret, creates Payment + active_ledger entry.
    """
    _verify_webhook_secret(request)

    payment = await process_crypto_webhook(body, session)

    return {
        "status": "ok",
        "payment_id": str(payment.id),
        "payment_status": payment.status,
    }
