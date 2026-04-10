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
#
# NULL HANDLING IN UserUpdate:
#   All fields are Optional with default=None. "Not sent" vs "explicit null"
#   is distinguished by exclude_unset in the service layer:
#     - Field not in request body -> not in model_dump(exclude_unset=True)
#     - Field set to null in JSON -> present with value None
#   Service layer rejects explicit null for NOT NULL DB columns (language).
#
# Sprint 6.3: payout_details schemas for withdrawal payment methods.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


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
    payout_details: dict[str, Any] | None = None
    language: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """PATCH /api/v1/users/me -- updatable profile fields.

    All fields are optional. Only provided fields are updated
    (exclude_unset in service layer).

    profile: merged with existing JSONB via set_jsonb().
    language: direct assignment. NOT NULL in DB -- explicit null
    is rejected in service layer, not here (avoids conflict with
    Pydantic default=None for "not sent" semantics).
    """

    profile: dict[str, Any] | None = Field(default=None)
    language: str | None = Field(default=None, min_length=1, max_length=10)


# ---------------------------------------------------------------------------
# Payout details (Sprint 6.3)
# ---------------------------------------------------------------------------


class UpdatePayoutDetailsRequest(BaseModel):
    """PUT /api/v1/users/me/payout-details -- set withdrawal payment methods.

    Free-form JSONB. Validation of specific methods (crypto, IBAN, etc.)
    will be added in future sprints when payment provider is integrated.
    """

    payout_details: dict[str, Any]


class PayoutDetailsResponse(BaseModel):
    """Response for GET /api/v1/users/me/payout-details."""

    payout_details: dict[str, Any] | None = None

    model_config = {"from_attributes": True}
