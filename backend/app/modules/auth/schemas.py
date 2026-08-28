# =============================================================================
# AIVIS.ONE Backend -- Auth Schemas
# =============================================================================
#
# Pydantic models for auth request/response validation.
#
# Sprint 1.1: EmailRegisterRequest, EmailLoginRequest, AuthResponse
# Sprint 1.2: TelegramAuthRequest
# Sprint 7.2: +referral_code on register + telegram requests
# G1 fix: +VerifyEmailRequest for email verification
# Password reset: +PasswordResetRequest / PasswordResetConfirmRequest
#   (both unauthenticated -- see auth/service.py module note)
# TASK-38: +SessionItemResponse / SessionListResponse -- GET /sessions.
#   session_id is a non-reversible public id (SHA-256 of the bearer
#   token, see auth/service.py's "PUBLIC SESSION ID" module note) --
#   never the raw token itself.
# TASK-38 (2FA): +TwoFactorSetupRequest/Response, TwoFactorConfirmRequest/
#   Response, TwoFactorDisableRequest, TwoFactorLoginVerifyRequest,
#   LoginResponse. See auth/router.py's "2FA" section header for the
#   full endpoint list and auth/service.py / users/service.py for the
#   storage shape and verification logic.
#
#   LoginResponse REPLACES AuthResponse as the response_model for
#   POST /auth/email/login AND POST /auth/telegram (NOT
#   /auth/email/register -- a brand-new account cannot have 2FA
#   enabled yet). Both login paths can now resolve to one of two
#   states -- a real session (mfa_required=False, user +
#   session_token populated, identical in shape to the old
#   AuthResponse) or a pending second factor (mfa_required=True,
#   mfa_token populated, user/session_token null). A flat model with
#   both branches' fields optional, rather than a Union/oneOf: the
#   in-house OpenAPI -> TypeScript generator
#   (scripts/generate_ts_types.py) explicitly does not support oneOf/
#   discriminator (see its own module docstring) -- it would silently
#   degrade a Union to `unknown` on the frontend. A single flat model
#   generates a normal interface with two nullable pairs, which the
#   frontend narrows itself on `mfa_required` (see stores/auth.ts).
# =============================================================================

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.modules.users.schemas import UserResponse


# ---------------------------------------------------------------------------
# Email Auth (Sprint 1.1)
# ---------------------------------------------------------------------------


class EmailRegisterRequest(BaseModel):
    """POST /api/v1/auth/email/register -- request body."""

    email: EmailStr = Field(
        ...,
        description="User email address (normalized to lowercase)",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 characters)",
    )
    # Sprint 7.2: optional referral code from agent link.
    referral_code: str | None = Field(
        default=None,
        max_length=20,
        description="Referral code from agent link (optional)",
    )


class EmailLoginRequest(BaseModel):
    """POST /api/v1/auth/email/login -- request body."""

    email: EmailStr
    password: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Email Verification (G1)
# ---------------------------------------------------------------------------


class VerifyEmailRequest(BaseModel):
    """POST /api/v1/auth/verify-email -- request body."""

    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit verification code",
    )


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------


class PasswordResetRequest(BaseModel):
    """POST /api/v1/auth/password-reset/request -- request body.

    Unauthenticated (no `user`, no session -- that is the whole point).
    The router returns the exact same response regardless of whether
    `email` matches a real account (anti-enumeration -- see
    auth/service.py::request_password_reset).
    """

    email: EmailStr = Field(
        ...,
        description="Account email to send the reset link to",
    )


class PasswordResetRequestResponse(BaseModel):
    """POST /api/v1/auth/password-reset/request -- response body.

    The router returns this EXACT SAME instance (same `message`, same
    200 status) whether or not `email` matched an account -- there is
    no field here that could vary and leak the match either.
    """

    message: str = (
        "If that email is registered, a password reset link has been sent."
    )


class PasswordResetConfirmRequest(BaseModel):
    """POST /api/v1/auth/password-reset/confirm -- request body.

    `new_password` reuses EmailRegisterRequest.password's exact
    constraints (min 8 / max 128 chars) -- password strength rules
    live in one place, not duplicated per endpoint.
    """

    token: str = Field(
        ...,
        min_length=1,
        description="Reset token from the emailed link",
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (min 8 characters)",
    )


# ---------------------------------------------------------------------------
# Telegram Auth (Sprint 1.2)
# ---------------------------------------------------------------------------


class TelegramAuthRequest(BaseModel):
    """POST /api/v1/auth/telegram -- request body."""

    init_data: str = Field(
        ...,
        min_length=1,
        description="Raw initData string from Telegram WebApp",
    )
    # Sprint 7.2: optional referral code from agent link.
    referral_code: str | None = Field(
        default=None,
        max_length=20,
        description="Referral code from agent link (optional)",
    )


# ---------------------------------------------------------------------------
# Response (shared by all auth methods)
# ---------------------------------------------------------------------------


class AuthResponse(BaseModel):
    """Response for POST /auth/email/register and POST /auth/2fa/login-verify.

    Also the shape of a SUCCESSFUL (mfa_required=False) email/telegram
    login before TASK-38 2FA -- login and telegram now respond with
    LoginResponse instead (see module note above), but its "real
    session" branch carries the exact same two fields.
    """

    user: UserResponse
    session_token: str


# ---------------------------------------------------------------------------
# Two-Factor Authentication -- TOTP (TASK-38)
# ---------------------------------------------------------------------------


class LoginResponse(BaseModel):
    """Response for POST /auth/email/login and POST /auth/telegram.

    Two mutually exclusive shapes, discriminated by `mfa_required`:
      - mfa_required=False (the common case, no 2FA on this account):
        `user` + `session_token` populated -- a real, usable session,
        identical to what AuthResponse used to carry from these two
        endpoints.
      - mfa_required=True (credentials.totp.enabled on this account):
        `mfa_token` populated, `user`/`session_token` are null. NO
        session has been created. The caller must complete
        POST /auth/2fa/login-verify with this mfa_token plus a live
        TOTP code (or an unused backup code) before a session exists --
        see auth/service.py's 2FA module note for the full flow and
        why a session is not issued at this point.
    """

    mfa_required: bool = False
    mfa_token: str | None = Field(
        default=None,
        description=(
            "Opaque single-use token for POST /auth/2fa/login-verify. "
            "Only set when mfa_required=true."
        ),
    )
    user: UserResponse | None = None
    session_token: str | None = None


class TwoFactorSetupRequest(BaseModel):
    """POST /api/v1/auth/2fa/setup -- request body.

    Re-authentication (current password) before a new pending TOTP
    secret can even be generated -- mirrors
    users/service.py::_require_current_password's use in
    request_email_change / deactivate_own_account.
    """

    current_password: str = Field(..., min_length=1)


class TwoFactorSetupResponse(BaseModel):
    """POST /api/v1/auth/2fa/setup -- response body.

    `secret` is the raw base32 TOTP secret -- standard practice to
    return it alongside the QR-encodable `provisioning_uri` so an
    authenticator app that cannot scan a QR code (or a user without a
    camera-equipped device) can enter it manually. Neither value is
    retrievable again after this response; a caller that loses it must
    call /2fa/setup again, which overwrites the pending secret (see
    users/service.py::setup_totp).
    """

    secret: str
    provisioning_uri: str


class TwoFactorConfirmRequest(BaseModel):
    """POST /api/v1/auth/2fa/confirm -- request body.

    Same 6-digit numeric shape as VerifyEmailRequest -- this is the
    first LIVE code computed from the pending secret, proving the user
    actually set up their authenticator app correctly before 2FA is
    switched on.
    """

    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit TOTP code from the authenticator app",
    )


class TwoFactorConfirmResponse(BaseModel):
    """POST /api/v1/auth/2fa/confirm -- response body.

    THE BACKUP CODES ARE SHOWN EXACTLY ONCE, HERE, IN PLAINTEXT. Only
    their argon2 hashes are stored (users/service.py::confirm_totp_setup)
    -- there is no "view my backup codes again" endpoint and there
    never will be with this storage shape. The frontend MUST treat this
    response as a "save these now" moment (a persistent, copyable /
    printable list), not a toast that can be dismissed and lost -- see
    components/shared/TwoFactorSection.vue.
    """

    backup_codes: list[str] = Field(
        ...,
        description="Single-use recovery codes, shown once. Store them somewhere safe.",
    )


class TwoFactorDisableRequest(BaseModel):
    """POST /api/v1/auth/2fa/disable -- request body.

    BOTH factors required, not either/or: disabling removes a security
    control, so proof of the password alone (which a stolen session
    already implies the caller has authenticated with) is not enough --
    see auth/router.py's 2FA section header for the full reasoning.
    `code` accepts either a live 6-digit TOTP code or an unused backup
    code (see users/service.py::disable_totp), hence the looser length
    bound than TwoFactorConfirmRequest's strict 6-digit pattern.
    """

    current_password: str = Field(..., min_length=1)
    code: str = Field(..., min_length=6, max_length=20)


class TwoFactorLoginVerifyRequest(BaseModel):
    """POST /api/v1/auth/2fa/login-verify -- request body.

    UNAUTHENTICATED (no session exists yet -- that is the entire point,
    same discipline as PasswordResetRequest/Confirm). `mfa_token` is
    the opaque value returned by LoginResponse.mfa_token; `code` is
    either a live TOTP code or an unused backup code, same acceptance
    as TwoFactorDisableRequest.code.
    """

    mfa_token: str = Field(..., min_length=1)
    code: str = Field(..., min_length=6, max_length=20)


# ---------------------------------------------------------------------------
# Active sessions (TASK-38)
# ---------------------------------------------------------------------------


class SessionItemResponse(BaseModel):
    """One entry in GET /api/v1/auth/sessions.

    session_id is DELIBERATELY NOT the bearer token -- it is a
    non-reversible SHA-256 hash of it (auth/service.py's
    _session_public_id). Holding this value grants no access; it only
    identifies which session to target in
    DELETE /api/v1/auth/sessions/{session_id}.
    """

    session_id: str = Field(
        ...,
        description="Non-reversible public id for this session (not the bearer token)",
    )
    created_at: datetime
    auth_method: str
    ip: str
    user_agent: str
    is_current: bool = Field(
        ...,
        description="True for the session making this very request",
    )


class SessionListResponse(BaseModel):
    """GET /api/v1/auth/sessions -- response body."""

    items: list[SessionItemResponse]
