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

from pydantic import BaseModel, EmailStr, Field, field_validator

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
#
# Narrowed to investor-only (TASK-30 admin-capability gap, joint owner
# investigation): self-selecting "company" set user.role with no
# CompanyProfile row -- every self-service company endpoint requires one
# and 403s without it, so that path produced a permanently broken
# account. Self-selecting "agent" bypassed the already-built
# POST /agent-applications -> staff review queue entirely. Company is
# now reachable only via admin assignment (POST /staff/companies/assign);
# agent stays reachable only via the application flow. Enforced here too
# (not just by hiding the UI cards) so a direct API call can't recreate
# either bug.
_SELECTABLE_ROLES = {"investor"}


class SelectRoleRequest(BaseModel):
    """POST /api/v1/users/me/select-role -- onboarding role selection."""

    role: str = Field(
        ...,
        description="Target role: investor (the only self-selectable role).",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Only investor is selectable during onboarding."""
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


# ---------------------------------------------------------------------------
# Email change (TASK-38)
# ---------------------------------------------------------------------------
#
# Three-step flow, mirroring auth/service.py's onboarding email
# verification shape but kept ENTIRELY SEPARATE from it (own JSONB
# slot: credentials.email_change, own endpoints under /me/email-change):
#   1. POST /me/email-change          -- current password + new email.
#      Verifies the password, checks the new email isn't already taken,
#      generates a 6-digit code, emails it to the NEW address, stores
#      the pending change (never touches credentials.email.email yet).
#   2. POST /me/email-change/resend   -- regenerate + resend the code.
#   3. POST /me/email-change/confirm  -- 6-digit code. On match, swaps
#      credentials.email.email to the pending value and clears the
#      pending slot.
# See users/service.py for why this is a separate endpoint rather than
# folded into UserUpdate/update_user -- email lives in credentials
# JSONB, not a plain User column, and changing the LOGIN identifier
# needs its own re-authentication + re-verification gate that has no
# equivalent for the profile fields UserUpdate covers.


class RequestEmailChangeRequest(BaseModel):
    """POST /api/v1/users/me/email-change -- request body.

    current_password re-authenticates the request (changing the login
    identifier is sensitive -- see users/service.py module note).
    new_email is normalized to lowercase in the service layer, same as
    register_email.
    """

    current_password: str = Field(..., min_length=1)
    new_email: EmailStr = Field(
        ...,
        description="New email address to move the account to",
    )


class ResendEmailChangeRequest(BaseModel):
    """POST /api/v1/users/me/email-change/resend -- empty body.

    No fields: the pending change (and its recipient) is already on
    the authenticated user's own credentials.email_change -- nothing
    for the caller to supply. Kept as an explicit model (rather than no
    body at all) for parity with VerifyEmailRequest's sibling shape and
    so FastAPI's OpenAPI schema documents the endpoint consistently.
    """

    model_config = {"extra": "forbid"}


class ConfirmEmailChangeRequest(BaseModel):
    """POST /api/v1/users/me/email-change/confirm -- request body.

    Same 6-digit shape as auth.VerifyEmailRequest -- deliberately not
    imported from there to keep the two verification flows
    independently evolvable (users vs auth domain).
    """

    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit verification code sent to the new email",
    )


# ---------------------------------------------------------------------------
# Self-deactivation (TASK-38)
# ---------------------------------------------------------------------------


class DeactivateAccountRequest(BaseModel):
    """POST /api/v1/users/me/deactivate -- request body.

    current_password confirms a destructive-feeling (though reversible
    -- see users/service.py module note) action, same re-auth pattern
    as RequestEmailChangeRequest.
    """

    current_password: str = Field(..., min_length=1)
