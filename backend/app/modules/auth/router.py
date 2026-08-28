# =============================================================================
# AIVIS.ONE Backend -- Auth Router (G1 fix)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/auth/email/register      -- Register via email + password
#   POST /api/v1/auth/email/login         -- Login via email + password
#   POST /api/v1/auth/telegram            -- Login via Telegram WebApp (Sprint 1.2)
#   POST /api/v1/auth/verify-email        -- Verify 6-digit email code (G1)
#   POST /api/v1/auth/verify-email/resend -- Resend verification code (G1)
#   POST /api/v1/auth/password-reset/request -- Request password reset link
#                                                (UNAUTHENTICATED, see note)
#   POST /api/v1/auth/password-reset/confirm -- Consume token, set new
#                                                password (UNAUTHENTICATED)
#   POST /api/v1/auth/logout              -- Logout current session
#   POST /api/v1/auth/logout-all          -- Logout all sessions (blocked in
#                                             avatar mode, R49 -- see
#                                             auth/avatar_guard.py's
#                                             logout_all note)
#
# PASSWORD RESET is deliberately UNAUTHENTICATED (no get_current_user_write):
#   the entire premise is that the caller is locked out and has no
#   session. Anti-enumeration lives in the router, not the service --
#   auth_password_reset_request() returns the same status + body whether
#   or not the email matched, regardless of what request_password_reset()
#   did internally. See auth/service.py's "PASSWORD RESET" module note
#   for the token design (Redis reverse-index, not credentials JSONB).
#
# RATE LIMITING (SEC-5):
#   Email register and login are rate-limited by IP address.
#   Uses same config as Telegram auth: auth_rate_limit_max_requests /
#   auth_rate_limit_window_seconds.
#   Key: "email_auth:{ip}" -- shared between register and login.
#   Resend: rate-limited per user_id (1 per 60s).
#   Key: "password_reset:{ip}" -- shared between request and confirm,
#   same shared-key shape as email_auth above. Both endpoints send no
#   auth-required signal an attacker could be blocked on otherwise (no
#   session, no password to get wrong) -- IP rate limiting is the only
#   throttle available on either one.
#
# REFERRAL (Sprint 7.2):
#   referral_code is passed from request body to service layer.
#   Resolution happens in service -- router just forwards.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

import structlog
from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.core.database import get_db_session
from app.core.exceptions import BadRequestError
from app.core.rate_limit import check_rate_limit
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.auth.schemas import (
    AuthResponse,
    EmailLoginRequest,
    EmailRegisterRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    TelegramAuthRequest,
    VerifyEmailRequest,
)
from app.modules.auth.service import (
    confirm_password_reset,
    create_session,
    delete_all_sessions,
    delete_session,
    login_email,
    register_email,
    request_password_reset,
    resend_verification_code,
    upsert_telegram_user,
    verify_email_code,
)
from app.modules.auth.telegram import (
    TelegramValidationError,
    check_auth_rate_limit,
    check_init_data_replay,
    validate_telegram_init_data,
)
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse
from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Register a new user via email + password."""
    # Rate limit by IP (SEC-5).
    ip = get_client_ip(request)
    await check_rate_limit(f"email_auth:{ip}")

    user = await register_email(
        body.email,
        body.password,
        session,
        background_tasks,
        referral_code=body.referral_code,
    )
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
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Login via email + password."""
    # Rate limit by IP (SEC-5).
    ip = get_client_ip(request)
    await check_rate_limit(f"email_auth:{ip}")

    user = await login_email(body.email, body.password, session, background_tasks)
    token = await create_session(user, auth_method="email")

    return AuthResponse(
        user=UserResponse.model_validate(user),
        session_token=token,
    )


# ---------------------------------------------------------------------------
# Email Verification (G1)
# ---------------------------------------------------------------------------


@router.post(
    "/verify-email",
    response_model=UserResponse,
)
async def auth_verify_email(
    body: VerifyEmailRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Verify email with 6-digit code sent during registration."""
    updated_user = await verify_email_code(user, body.code, session)
    return UserResponse.model_validate(updated_user)


@router.post(
    "/verify-email/resend",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def auth_resend_verification(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Resend verification code. Rate-limited: 1 per 60 seconds."""
    # Uses default auth rate limit config (5 per 60s). Acceptable for MVP.
    await check_rate_limit(f"email_verify_resend:{user.id}")
    await resend_verification_code(user, session, background_tasks)


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------

# Fixed response instance for BOTH branches (anti-enumeration) -- built
# once, returned unchanged whether or not the email matched. See the
# router header note and PasswordResetRequestResponse's docstring.
_PASSWORD_RESET_REQUEST_RESPONSE = PasswordResetRequestResponse()


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResponse,
)
async def auth_password_reset_request(
    body: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> PasswordResetRequestResponse:
    """Request a password reset link. UNAUTHENTICATED -- no session exists.

    Rate limited by IP (shared "password_reset:{ip}" key with confirm,
    see router header). Anti-enumeration: request_password_reset()
    internally branches on whether the email matched, but this handler
    does not -- it always returns the same fixed response object, so
    there is nothing here for a caller to distinguish.
    """
    ip = get_client_ip(request)
    await check_rate_limit(f"password_reset:{ip}")

    await request_password_reset(body.email, session, background_tasks)

    return _PASSWORD_RESET_REQUEST_RESPONSE


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def auth_password_reset_confirm(
    body: PasswordResetConfirmRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Consume a reset token and set a new password. UNAUTHENTICATED.

    Rate limited by IP (shared "password_reset:{ip}" key with request,
    see router header). Unlike request, this endpoint's response DOES
    reveal whether the token was valid (400 vs 204) -- that is
    unavoidable and not an enumeration risk: the token is a 256-bit
    secret only the recipient of the reset email ever saw, not
    something derivable from an email address.
    """
    ip = get_client_ip(request)
    await check_rate_limit(f"password_reset:{ip}")

    await confirm_password_reset(body.token, body.new_password, session)


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
    # iter 2.5-finishing: rate-limit hits raise RateLimitError (HTTP 429)
    # and propagate to the global AivisError handler unchanged. Earlier
    # revisions caught and remapped them to 400 alongside invalid-signature
    # and replay errors -- that masked the rate-limit signal. Invalid
    # signature and replay still raise TelegramValidationError above and
    # get the 400 mapping; only rate-limit gets the dedicated 429.
    await check_auth_rate_limit(telegram_user["id"])

    # Step 4: Upsert user (flush inside service, not here).
    user, _is_new = await upsert_telegram_user(
        telegram_user,
        session,
        referral_code=body.referral_code,
    )

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


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    # R49 / STAGE-III-FINDINGS.md #19: an avatar must not be able to end
    # every session the REAL owner holds while its own session survives.
    dependencies=[Depends(forbid_avatar("logout_all"))],
)
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
