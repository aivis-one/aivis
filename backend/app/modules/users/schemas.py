# =============================================================================
# AIVIS.ONE Backend -- User Schemas
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
# NULL HANDLING IN UserUpdate:
#   All fields are Optional with default=None. "Not sent" vs "explicit null"
#   is distinguished by exclude_unset in the service layer:
#     - Field not in request body -> not in model_dump(exclude_unset=True)
#     - Field set to null in JSON -> present with value None
#   Service layer rejects explicit null for NOT NULL DB columns (language).
#
# Sprint 6.3: payout_details schemas for withdrawal payment methods.
# F2.3: SelectRoleRequest for onboarding role selection.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.modules.staff.schemas import StaffProfileResponse


class UserResponse(BaseModel):
    """User representation in API responses.

    Excludes credentials (sensitive: password hashes, tokens).
    Profile is returned as-is from JSONB.
    Email is extracted from credentials via User.email property.

    iter 2.6c B6:
      `staff_profile` is populated by the service layer when
      `role == "staff"` -- it carries the staff profile id, is_active
      flag, and the EFFECTIVE permission matrix (defaults merged with
      per-staff overrides). For non-staff users the field is null.
      The frontend Staff Platform tab keys off this field to gate the
      whole surface.
    """

    id: UUID
    role: str
    email: str | None = Field(default=None, description="User email address")
    is_active: bool
    onboarding_step: str
    kyc_status: str
    profile: dict[str, Any]
    payout_details: dict[str, Any] | None = None
    language: str
    created_at: datetime
    updated_at: datetime | None = None
    staff_profile: StaffProfileResponse | None = None

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
# Role selection (F2.3 -- Onboarding)
# ---------------------------------------------------------------------------

# Roles selectable during onboarding (staff and platform excluded).
_SELECTABLE_ROLES = {"investor", "agent", "company"}


class SelectRoleRequest(BaseModel):
    """POST /api/v1/users/me/select-role -- onboarding role selection."""

    role: str = Field(
        ...,
        description="Target role: investor, agent, or company",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Only investor, agent, company are selectable during onboarding."""
        if v not in _SELECTABLE_ROLES:
            raise ValueError(
                f"Invalid role: {v}. Must be one of: "
                f"{', '.join(sorted(_SELECTABLE_ROLES))}"
            )
        return v


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
