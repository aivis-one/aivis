# =============================================================================
# CBSHOME Backend -- Auth Router
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/auth/email/register  -- Register via email + password
#   POST /api/v1/auth/email/login     -- Login via email + password
#   POST /api/v1/auth/telegram        -- Login via Telegram WebApp (Sprint 1.2)
#   POST /api/v1/auth/logout          -- Logout current session
#   POST /api/v1/auth/logout-all      -- Logout all sessions
#
# RATE LIMITING (SEC-5):
#   Email register and login are rate-limited by IP address.
#   Uses same config as Telegram auth: auth_rate_limit_max_requests /
#   auth_rate_limit_window_seconds.
#   Key: "email_auth:{ip}" -- shared between register and login.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.exceptions import BadRequestError
from app.core.rate_limit import check_rate_limit
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import (
    AuthResponse,
    EmailLoginRequest,
    EmailRegisterRequest,
    TelegramAuthRequest,
)
from app.modules.auth.service import (
    create_session,
    delete_all_sessions,
    delete_session,
    login_email,
    register_email,
    upsert_telegram_user,
)
from app.modules.auth.telegram import (
    TelegramValidationError,
    check_auth_rate_limit,
    check_init_data_replay,
    validate_telegram_init_data,
)
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Real-IP header (set by Nginx).

    Falls back to request.client.host for dev/test environments.
    """
    return (
        request.headers.get("X-Real-IP")
        or (request.client.host if request.client else "unknown")
    )


# ---------------------------------------------------------------------------
# Email Auth (Sprint 1.1)
# ---------------------------------------------------------------------------


@router.post(
    "/email/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def auth_email_register(
    body: EmailRegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Register a new user via email + password."""
    # Rate limit by IP (SEC-5).
    ip = _get_client_ip(request)
    await check_rate_limit(f"email_auth:{ip}")

    user = await register_email(body.email, body.password, session)
    token = await create_session(user, auth_method="email")

    return AuthResponse(
        user=UserResponse.model_validate(user),
        session_token=token,
    )


@router.post(
    "/email/login",
    response_model=AuthResponse,
)
async def auth_email_login(
    body: EmailLoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Login via email + password."""
    # Rate limit by IP (SEC-5).
    ip = _get_client_ip(request)
    await check_rate_limit(f"email_auth:{ip}")

    user = await login_email(body.email, body.password, session)
    token = await create_session(user, auth_method="email")

    return AuthResponse(
        user=UserResponse.model_validate(user),
        session_token=token,
    )


# ---------------------------------------------------------------------------
# Telegram Auth (Sprint 1.2)
# ---------------------------------------------------------------------------


@router.post(
    "/telegram",
    response_model=AuthResponse,
)
async def auth_telegram(
    body: TelegramAuthRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Authenticate via Telegram WebApp.

    Flow:
      1. Validate initData signature (HMAC-SHA256)
      2. Anti-replay: reject reused initData (Redis SET NX)
      3. Rate limit per telegram_id (Redis INCR + EXPIRE)
      4. Find or create User by telegram_id in credentials JSONB
      5. Create Redis session
      6. Return AuthResponse
    """
    # Step 1: Validate initData from Telegram.
    try:
        telegram_user = validate_telegram_init_data(
            body.init_data,
            settings.telegram_bot_token,
        )
    except TelegramValidationError as exc:
        logger.warning("telegram_auth_failed", reason=str(exc))
        raise BadRequestError(str(exc)) from exc

    # Step 2: Anti-replay.
    try:
        await check_init_data_replay(body.init_data)
    except TelegramValidationError as exc:
        logger.warning("telegram_auth_replay", reason=str(exc))
        raise BadRequestError(str(exc)) from exc

    # Step 3: Rate limit.
    try:
        await check_auth_rate_limit(telegram_user["id"])
    except TelegramValidationError as exc:
        logger.warning(
            "telegram_auth_rate_limited",
            telegram_id=telegram_user["id"],
        )
        raise BadRequestError(str(exc)) from exc

    # Step 4: Upsert user (flush inside service, not here).
    user, _is_new = await upsert_telegram_user(telegram_user, session)

    # Step 5: Create Redis session.
    token = await create_session(user, auth_method="telegram")

    return AuthResponse(
        user=UserResponse.model_validate(user),
        session_token=token,
    )


# ---------------------------------------------------------------------------
# Logout (Sprint 1.1)
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def auth_logout(
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Logout current session -- delete from Redis."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    if token:
        await delete_session(token, user_id=user.id)

    logger.info("user_logout", user_id=str(user.id))


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def auth_logout_all(
    user: User = Depends(get_current_user),
) -> None:
    """Logout all sessions for the current user."""
    count = await delete_all_sessions(user.id)

    logger.info(
        "user_logout_all",
        user_id=str(user.id),
        sessions_invalidated=count,
    )
