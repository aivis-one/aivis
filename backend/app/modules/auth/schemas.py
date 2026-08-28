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
    """Response for all auth endpoints (register, login, telegram)."""

    user: UserResponse
    session_token: str


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
