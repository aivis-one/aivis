# =============================================================================
# CBSHOME Backend -- Auth Schemas
# =============================================================================
#
# Pydantic models for auth request/response validation.
#
# Sprint 1.1: EmailRegisterRequest, EmailLoginRequest, AuthResponse
# Sprint 1.2: TelegramAuthRequest
# =============================================================================

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


class EmailLoginRequest(BaseModel):
    """POST /api/v1/auth/email/login -- request body."""

    email: EmailStr
    password: str = Field(..., min_length=1)


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


# ---------------------------------------------------------------------------
# Response (shared by all auth methods)
# ---------------------------------------------------------------------------


class AuthResponse(BaseModel):
    """Response for all auth endpoints (register, login, telegram)."""

    user: UserResponse
    session_token: str
