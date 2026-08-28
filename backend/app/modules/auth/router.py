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
#   GET /api/v1/auth/sessions             -- List caller's own active
#                                             sessions (TASK-38)
#   DELETE /api/v1/auth/sessions/{id}     -- Revoke one session by its
#                                             public id (TASK-38, blocked
#                                             in avatar mode -- see
#                                             avatar_guard.py's
#                                             revoke_session note)
#   POST /api/v1/auth/2fa/setup           -- Start/restart TOTP setup
#                                             (TASK-38, avatar-blocked)
#   POST /api/v1/auth/2fa/confirm         -- Confirm setup, turn 2FA on,
#                                             issue backup codes ONCE
#                                             (TASK-38, avatar-blocked)
#   POST /api/v1/auth/2fa/disable         -- Turn 2FA off (TASK-38,
#                                             avatar-blocked)
#   POST /api/v1/auth/2fa/login-verify    -- Complete a 2FA-gated login
#                                             (TASK-38, UNAUTHENTICATED,
#                                             see note below)
#
# ACTIVE SESSIONS (TASK-38): session_id in the list/revoke pair below is
# NEVER the bearer token -- see auth/service.py's "PUBLIC SESSION ID"
# module note for the exact SHA-256 mechanism and why a response body
# must never carry a live credential.
#
# TWO-FACTOR AUTHENTICATION (TOTP, TASK-38):
#   Storage shape, verification logic, and the setup/confirm/disable
#   service functions are documented in users/service.py's "Two-Factor
#   Authentication (TOTP)" module note (setup/confirm/disable live
#   there, not in auth/service.py -- see that note for why: they need
#   users/service.py::_require_current_password, and auth/service.py
#   cannot import back from users/service.py without a circular
#   import). auth/service.py owns the login-time half:
#   verify_totp_or_backup_code (shared by disable_totp there and
#   verify_2fa_login here) and the pending-MFA-token mechanism below.
#
#   THE LOGIN-TIME GATE. auth_email_login and auth_telegram both used to
#   call create_session() the moment login_email()/upsert_telegram_user()
#   succeeded and return AuthResponse unconditionally. Now: if the
#   authenticated account has credentials.totp.enabled=True, NEITHER
#   endpoint creates a session. Instead each mints a short-lived,
#   single-use "pending MFA" token (create_mfa_pending_token,
#   auth/service.py -- a SEPARATE Redis mechanism from a real session,
#   5-minute TTL) and returns LoginResponse(mfa_required=True,
#   mfa_token=...) with `user`/`session_token` left null. The caller
#   then calls POST /2fa/login-verify with that token plus a live code;
#   ONLY on success does a real session get created there.
#
#   BOTH auth_email_login AND auth_telegram now respond with
#   LoginResponse instead of AuthResponse (see schemas.py's LoginResponse
#   docstring for why a flat model, not a Union). register_email is
#   UNCHANGED (still AuthResponse) -- a brand-new account cannot have
#   2FA enabled yet, so there is nothing to gate.
#
#   TELEGRAM ALSO HONOURS 2FA, DELIBERATELY, NOT JUST EMAIL/PASSWORD.
#   A Telegram-linked account can independently have email+password+2FA
#   set up (upsert_telegram_user only ever touches credentials.telegram,
#   never credentials.totp) -- gating only the email/password path would
#   leave a real, silent bypass: anyone who could authenticate as that
#   Telegram identity (a stolen Telegram session, a SIM-swap-adjacent
#   takeover of the linked Telegram account, or simply the account
#   owner using both surfaces) would walk straight past a 2FA control
#   the account owner deliberately turned on, defeating the entire
#   point of building it. The cost: the standalone SPA (not the
#   Telegram Mini App context) is where 2FA code entry actually lives
#   today (LoginView.vue) -- a Telegram Mini App user with 2FA enabled
#   currently sees useAuth.ts surface an honest "complete verification
#   in a browser" message rather than either a silent bypass or a
#   broken hang. See useAuth.ts's own note for that tradeoff, flagged
#   as a known gap rather than shipped silently.
#
#   POST /2fa/login-verify IS UNAUTHENTICATED -- same discipline as
#   password-reset's pair of endpoints (see that section below): the
#   caller has no session by construction, that is the entire point.
#   Rate-limited aggressively and independently of the token's own
#   single-use consumption -- see auth/service.py's
#   _MFA_PENDING_TTL_SECONDS module note for the full reasoning
#   (a 6-digit TOTP code is a small space, and the token being consumed
#   on every outcome -- success OR failure -- is the primary defense;
#   the IP rate limit below is the second, independent layer, capping
#   how fast fresh tokens can be minted via repeated correct-password
#   logins in the first place).
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
#   Resend: rate-limited per user_id, same shared auth_rate_limit_max_requests
#   / window_seconds default as above (5 per 60s out of the box, not a
#   bespoke 1-per-60s -- a stale docstring claiming otherwise, directly
#   contradicting the comment beside its own check_rate_limit() call, was
#   caught and fixed while a later batch built an adjacent email-change
#   flow that copied the same wrong figure into a new docstring).
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
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.rate_limit import check_rate_limit
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.auth.schemas import (
    AuthResponse,
    EmailLoginRequest,
    EmailRegisterRequest,
    LoginResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    SessionItemResponse,
    SessionListResponse,
    TelegramAuthRequest,
    TwoFactorConfirmRequest,
    TwoFactorConfirmResponse,
    TwoFactorDisableRequest,
    TwoFactorLoginVerifyRequest,
    TwoFactorSetupRequest,
    TwoFactorSetupResponse,
    VerifyEmailRequest,
)
from app.modules.auth.service import (
    confirm_password_reset,
    create_mfa_pending_token,
    create_session,
    delete_all_sessions,
    delete_session,
    list_sessions,
    login_email,
    register_email,
    request_password_reset,
    resend_verification_code,
    revoke_session,
    upsert_telegram_user,
    verify_2fa_login,
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
from app.modules.users.service import confirm_totp_setup, disable_totp, setup_totp
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
    token = await create_session(
        user,
        auth_method="email",
        ip=ip,
        user_agent=request.headers.get("User-Agent", ""),
    )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        session_token=token,
    )


@router.post(
    "/email/login",
    response_model=LoginResponse,
)
async def auth_email_login(
    body: EmailLoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """Login via email + password.

    TASK-38: if this account has 2FA enabled (credentials.totp.enabled),
    NO session is created here -- see the module header's "TWO-FACTOR
    AUTHENTICATION" note. LoginResponse.mfa_required=True carries a
    pending token for POST /2fa/login-verify instead of a session_token.
    """
    # Rate limit by IP (SEC-5).
    ip = get_client_ip(request)
    await check_rate_limit(f"email_auth:{ip}")

    user = await login_email(body.email, body.password, session, background_tasks)

    totp_creds = (user.credentials or {}).get("totp") or {}
    if totp_creds.get("enabled"):
        mfa_token = await create_mfa_pending_token(user.id, auth_method="email")
        logger.info("login_requires_2fa", user_id=str(user.id), auth_method="email")
        return LoginResponse(mfa_required=True, mfa_token=mfa_token)

    token = await create_session(
        user,
        auth_method="email",
        ip=ip,
        user_agent=request.headers.get("User-Agent", ""),
    )

    return LoginResponse(
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
    """Resend verification code. Rate-limited via the shared default auth
    rate limit config (5 per 60s out of the box). Acceptable for MVP."""
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
    response_model=LoginResponse,
)
async def auth_telegram(
    body: TelegramAuthRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """Authenticate via Telegram WebApp.

    Flow:
      1. Validate initData signature (HMAC-SHA256)
      2. Anti-replay: reject reused initData (Redis SET NX)
      3. Rate limit per telegram_id (Redis INCR + EXPIRE)
      4. Find or create User by telegram_id in credentials JSONB
      5. TASK-38: if this account has 2FA enabled, return
         mfa_required=True instead of creating a session -- see the
         module header's "TELEGRAM ALSO HONOURS 2FA" note for why this
         path is gated too, not just email/password.
      6. Otherwise create Redis session, return LoginResponse

    request (TASK-38): this endpoint had no Request param before --
    the other two create_session() call sites already had one in scope
    for get_client_ip() rate-limiting, this one did not since Telegram
    auth is rate-limited per telegram_id (check_auth_rate_limit), not
    per IP. Added solely to capture ip/user_agent for the session list.
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

    # Step 5 (TASK-38): 2FA gate -- see module header note. A brand-new
    # user (is_new=True) can never reach this branch: upsert_telegram_user
    # only sets credentials.telegram, never credentials.totp.
    totp_creds = (user.credentials or {}).get("totp") or {}
    if totp_creds.get("enabled"):
        mfa_token = await create_mfa_pending_token(user.id, auth_method="telegram")
        logger.info(
            "login_requires_2fa", user_id=str(user.id), auth_method="telegram"
        )
        return LoginResponse(mfa_required=True, mfa_token=mfa_token)

    # Step 6: Create Redis session.
    token = await create_session(
        user,
        auth_method="telegram",
        ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )

    return LoginResponse(
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


# ---------------------------------------------------------------------------
# Active sessions (TASK-38)
# ---------------------------------------------------------------------------


@router.get(
    "/sessions",
    response_model=SessionListResponse,
)
async def auth_list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
) -> SessionListResponse:
    """List the caller's own active sessions, newest-first.

    is_current is computed by comparing each session's (internal-only)
    token against the caller's own bearer token, extracted the same way
    /logout already does it (Authorization header, "Bearer " prefix
    stripped). That raw token is used ONLY for this comparison and is
    never placed on the response model -- see service.py's
    "PUBLIC SESSION ID" module note and SessionItemResponse's docstring
    for why a live credential must never appear in this response.

    Not gated by forbid_avatar -- read-only visibility, same category
    as the rest of what avatar mode already exposes about the target
    user (see avatar_guard.py's revoke_session note for the asymmetry
    with the DELETE endpoint below).
    """
    auth_header = request.headers.get("Authorization", "")
    current_token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    sessions = await list_sessions(user.id)

    items = [
        SessionItemResponse(
            session_id=s["session_id"],
            created_at=s["created_at"],
            auth_method=s["auth_method"],
            ip=s["ip"],
            user_agent=s["user_agent"],
            is_current=(s["token"] == current_token),
        )
        for s in sessions
    ]

    return SessionListResponse(items=items)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # Same disruption-vector reasoning as logout_all, at single-device
    # granularity -- see avatar_guard.py's revoke_session note.
    dependencies=[Depends(forbid_avatar("revoke_session"))],
)
async def auth_revoke_session(
    session_id: str,
    user: User = Depends(get_current_user),
) -> None:
    """Revoke one of the caller's own sessions by its public id.

    Revoking the CALLER'S OWN current session is deliberately ALLOWED
    (not special-cased to redirect to /logout): revoke_session() is
    already scoped to this user's own sessions, so there is no extra
    privilege it grants over /logout -- self-revoking the current
    session here has the exact same effect. The frontend simply does
    not render a Revoke button on the is_current row (there is nothing
    unsafe about the backend allowing it if some other client did).

    404 -- not 403 -- when session_id does not resolve to one of the
    caller's own sessions. This covers two cases identically on
    purpose: the id does not exist at all, and the id belongs to a
    DIFFERENT user's session. revoke_session() scopes its scan to this
    user_id's own ZSET, so a foreign id can never match -- there is
    nothing here for a caller to distinguish, same "don't confirm what
    you can't prove the caller owns" discipline used across this
    codebase's other auth-adjacent 404s (see auth/dependencies.py's
    401-not-404 comment on a deleted user's session).
    """
    revoked = await revoke_session(user.id, session_id)
    if not revoked:
        raise NotFoundError("Session not found")


# ---------------------------------------------------------------------------
# Two-Factor Authentication (TOTP) -- TASK-38
# ---------------------------------------------------------------------------


@router.post(
    "/2fa/setup",
    response_model=TwoFactorSetupResponse,
    dependencies=[Depends(forbid_avatar("manage_2fa"))],
)
async def auth_2fa_setup(
    body: TwoFactorSetupRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorSetupResponse:
    """Start (or restart) TOTP setup. Requires the current password.

    Rate-limited per user (repeated calls regenerate a fresh pending
    secret -- real cost/abuse surface even though each call is
    individually harmless). Shared default cap
    (auth_rate_limit_max_requests / window_seconds, 5 per 60s out of
    the box), same shape as email_change_request's rate limit.
    """
    await check_rate_limit(f"totp_setup:{user.id}")
    secret, provisioning_uri = await setup_totp(user, body.current_password, session)
    return TwoFactorSetupResponse(secret=secret, provisioning_uri=provisioning_uri)


@router.post(
    "/2fa/confirm",
    response_model=TwoFactorConfirmResponse,
    dependencies=[Depends(forbid_avatar("manage_2fa"))],
)
async def auth_2fa_confirm(
    body: TwoFactorConfirmRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorConfirmResponse:
    """Confirm setup with a live code, turn 2FA on, issue backup codes.

    THE RESPONSE'S backup_codes ARE SHOWN EXACTLY ONCE -- see
    TwoFactorConfirmResponse's docstring. Rate-limited per user, same
    shared default cap as /2fa/setup above.
    """
    await check_rate_limit(f"totp_confirm:{user.id}")
    backup_codes = await confirm_totp_setup(user, body.code, session)
    return TwoFactorConfirmResponse(backup_codes=backup_codes)


@router.post(
    "/2fa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(forbid_avatar("manage_2fa"))],
)
async def auth_2fa_disable(
    body: TwoFactorDisableRequest,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Turn 2FA off. Requires BOTH the current password AND a live code
    (or an unused backup code) -- see TwoFactorDisableRequest's
    docstring. Rate-limited per user, same shared default cap as
    /2fa/setup above.
    """
    await check_rate_limit(f"totp_disable:{user.id}")
    await disable_totp(user, body.current_password, body.code, session)


@router.post(
    "/2fa/login-verify",
    response_model=AuthResponse,
)
async def auth_2fa_login_verify(
    body: TwoFactorLoginVerifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Complete a 2FA-gated login. UNAUTHENTICATED -- no session exists
    yet, see the module header's "TWO-FACTOR AUTHENTICATION" note.

    Rate limited by IP, TIGHTER than the shared auth default (5/60s):
    5 per 300s (5 minutes). A 6-digit TOTP code is a 1,000,000-value
    space and the pending token's own single-use-on-any-outcome
    consumption (auth/service.py::verify_2fa_login) is the PRIMARY
    defense -- this IP limit is the second, independent layer, and it
    is deliberately stricter than password_reset's/email_auth's 5/60s
    because TOTP's whole security model rests on the guess RATE, not
    the code space alone (unlike a 256-bit reset token, which is
    infeasible to guess regardless of rate). Keyed by IP rather than by
    mfa_token: the token is already destroyed after exactly one attempt
    (success or failure) by GETDEL, so a per-token limit would be
    redundant with that; IP is what actually caps how fast a caller can
    mint FRESH tokens via repeated correct-password logins and spend
    each one's single guess.
    """
    ip = get_client_ip(request)
    await check_rate_limit(
        f"totp_login_verify:{ip}",
        max_requests=5,
        window_seconds=300,
        error_message="Too many verification attempts. Please try again later.",
    )

    user, auth_method = await verify_2fa_login(body.mfa_token, body.code, session)
    token = await create_session(
        user,
        auth_method=auth_method,
        ip=ip,
        user_agent=request.headers.get("User-Agent", ""),
    )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        session_token=token,
    )
