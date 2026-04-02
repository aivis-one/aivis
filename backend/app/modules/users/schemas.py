# =============================================================================
# CBSHOME Backend -- User Schemas
# =============================================================================
#
# Pydantic models for user profile endpoints.
#
# UserResponse lives here (not in auth/) because it belongs to the users
# domain. auth/schemas.py imports it for AuthResponse.
#
# CREDENTIALS AND PROFILE:
#   credentials is NEVER exposed in UserResponse -- contains password
#   hashes and auth tokens. Profile is exposed as-is (JSONB dict).
#
# UserUpdate is defined here for Sprint 1.3 (PATCH /users/me).
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class UserResponse(BaseModel):
    """User representation in API responses.

    Excludes credentials (sensitive: password hashes, tokens).
    Profile is returned as-is from JSONB.
    """

    id: UUID
    role: str
    is_active: bool
    onboarding_step: str
    kyc_status: str
    profile: dict[str, Any]
    language: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """PATCH /api/v1/users/me -- updatable profile fields.

    All fields are optional. Only provided fields are updated
    (exclude_unset in service layer).

    profile: merged with existing JSONB via set_jsonb().
    language: direct assignment, NOT NULL in DB.
    """

    profile: dict[str, Any] | None = Field(default=None)
    language: str | None = Field(default=None, min_length=1, max_length=10)

    @field_validator("language", mode="before")
    @classmethod
    def reject_null_language(cls, v: str | None) -> str | None:
        """Reject explicit null for NOT NULL DB column.

        language has server_default='en' but cannot be set to NULL.
        Sending null would cause IntegrityError.
        """
        if v is None:
            raise ValueError("language cannot be set to null")
        return v
