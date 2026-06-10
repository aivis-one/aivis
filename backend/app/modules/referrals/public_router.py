# =============================================================================
# CBSHOME Backend -- Referral Public Router (Task 1 Block B)
# =============================================================================
#
# ENDPOINTS (no auth):
#   POST /api/v1/public/referral-click -> 204 No Content (always)
#
# SEMANTICS:
#   Fire-and-forget click counter for /r/:code landing traffic. The
#   frontend does not parse the response, so the endpoint answers 204
#   for both known and unknown codes -- a probe cannot confirm that a
#   code exists. Increment happens regardless of is_active: the click
#   occurred even if the agent later deactivated the link.
#
# RATE-LIMIT PER IP (anti-abuse, NOT click dedup):
#   Reuses core/rate_limit.check_rate_limit (Redis Lua, 429 +
#   Retry-After via RateLimitError -- same convention as the public
#   attachments/companies routers). Limits come from settings
#   (referral_click_rate_limit_*), key: public_referral_click:<ip>.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session manages it.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.rate_limit import check_rate_limit
from app.modules.referrals.schemas import ReferralClickRequest
from app.modules.referrals.service import record_click

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/public",
    tags=["referrals-public"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Real-IP header (set by Nginx).

    Falls back to request.client.host for dev/test environments.
    Mirrors auth/router._get_client_ip so the rate-limit key shape
    stays consistent across the codebase.
    """
    return (
        request.headers.get("X-Real-IP")
        or (request.client.host if request.client else "unknown")
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/referral-click",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def referral_click(
    body: ReferralClickRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Record a referral-link click. Public, fire-and-forget.

    Always 204 -- both on a matching and on an unknown code, so the
    response never confirms code existence. The only non-204 outcomes
    are 422 (payload fails the Pydantic schema, e.g. code longer than
    20 chars) and 429 (per-IP rate limit exceeded).
    """
    ip = _get_client_ip(request)
    await check_rate_limit(
        f"public_referral_click:{ip}",
        max_requests=settings.referral_click_rate_limit_max_requests,
        window_seconds=settings.referral_click_rate_limit_window_seconds,
        error_message="Too many requests. Please try again later.",
    )

    # Atomic DB-level increment; unknown codes are a silent no-op.
    await record_click(body.code, session)

    return None
