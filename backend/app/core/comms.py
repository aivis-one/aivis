# =============================================================================
# AIVIS.ONE Backend -- Comms client: the recipient must exist first (T-64)
# =============================================================================
#
# THE PROBLEM THIS SOLVES. comms delivers to KNOWN recipients only:
# Recipient.id is this product's user id. A notification aimed at a user
# comms has not heard of resolves to an empty audience, the notification
# is marked SKIPPED (terminal, no delivery row, no retry anywhere), and
# the message is gone -- silently. The outbox relay (T-63) syncs
# identities eventually, but "eventually" is exactly what a verification
# message emitted seconds after registration cannot wait for.
#
# So: when a user is created, comms is called SYNCHRONOUSLY and the
# recipient exists before anything is sent.
#
# WHAT THIS MODULE PROMISES, AND WHAT IT REFUSES TO PROMISE.
#   - It never raises. Registration must not become more fragile than it
#     is today: sending the verification e-mail already fails quietly, and
#     a comms outage must not cost a user their account.
#   - It does not retry. One attempt, one short timeout. The retry lives
#     in the outbox instead, where it survives restarts -- retrying here
#     would only make a registering user wait longer for the same answer.
#   - With no COMMS_API_URL configured it does nothing at all and says so
#     once. A box without a comms stack is a supported configuration.
#
# WHERE THE FALLBACK LIVES: not here. The caller (see
# modules/auth/service.py) emits a user_upserted outbox event in the SAME
# transaction when this returns False, so a failed synchronous call
# degrades to the asynchronous path instead of losing the recipient.
# =============================================================================

from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog

from app.core.config import settings

if TYPE_CHECKING:  # pragma: no cover -- annotation only
    # Imported for typing only: core must not depend on a product
    # module at runtime, but the snapshot below reads five specific
    # User attributes and typing them is the point of this function.
    from app.modules.users.models import User

logger = structlog.get_logger()

# The comms route this module speaks to (PUT /api/v1/recipients/{id}).
_RECIPIENTS_PATH = "/api/v1/recipients"


def comms_configured() -> bool:
    """True when this box has a comms address to talk to."""
    return bool(settings.comms_api_url)


def user_snapshot(user: "User") -> dict[str, Any]:
    """Build the identity snapshot comms stores for one user.

    A SNAPSHOT, not a patch: every field is always present and "no
    value" is an explicit None. comms overwrites what it holds with
    exactly this, so omitting a field would mean "keep the old value" --
    a semantic this contract does not have.

    timezone is always None: this product does not track a user
    timezone at all, and comms falls back to its own default when
    computing quiet hours. It is passed anyway, and explicitly, because
    the absence of the key is a different thing from the value None.
    """
    credentials = user.credentials or {}
    telegram = credentials.get("telegram") or {}
    telegram_id = telegram.get("id")
    return {
        "telegram_id": int(telegram_id) if telegram_id is not None else None,
        "email": user.email,
        "locale": user.language,
        "timezone": None,
        "active": user.is_active,
    }


async def upsert_recipient(recipient_id: UUID, snapshot: dict[str, Any]) -> bool:
    """Create or update the recipient in comms. Returns success.

    Never raises: every failure -- unconfigured, unreachable, refused,
    rejected -- is logged and reported as False, so the caller decides
    what to do about it. The caller is expected to fall back to the
    outbox rather than to fail the operation that triggered this.
    """
    if not comms_configured():
        # Not an error and not once per user: a box without comms says
        # this on every registration, which is why it is INFO with the
        # user id and not a warning.
        logger.info(
            "comms_upsert_skipped_no_url",
            recipient_id=str(recipient_id),
        )
        return False

    url = f"{settings.comms_api_url.rstrip('/')}{_RECIPIENTS_PATH}/{recipient_id}"
    headers = {"Authorization": f"Bearer {settings.comms_service_token}"}

    try:
        async with httpx.AsyncClient(
            timeout=settings.comms_http_timeout_seconds
        ) as client:
            response = await client.put(url, json=snapshot, headers=headers)
    except httpx.TimeoutException as exc:
        logger.warning(
            "comms_upsert_timeout",
            recipient_id=str(recipient_id),
            error=str(exc),
        )
        return False
    except httpx.HTTPError as exc:
        logger.warning(
            "comms_upsert_request_failed",
            recipient_id=str(recipient_id),
            error=str(exc),
        )
        return False

    if response.status_code in (401, 403):
        # Configuration, not weather: a wrong or empty service token
        # fails every call the same way and will not heal on its own.
        logger.error(
            "comms_upsert_unauthorized",
            recipient_id=str(recipient_id),
            status=response.status_code,
        )
        return False

    if response.status_code >= 400:
        logger.warning(
            "comms_upsert_rejected",
            recipient_id=str(recipient_id),
            status=response.status_code,
        )
        return False

    logger.info("comms_recipient_upserted", recipient_id=str(recipient_id))
    return True
