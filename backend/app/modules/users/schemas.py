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
# THE NAMES IN THE PROFILE (H43). profile.first_name and profile.last_name
# reach documents and e-mail letters (purchases/document_utils.py
# extract_investor_name, app/letters), and comms refuses a letter over its
# limits -- so every path that writes them holds them to one rule,
# profile_name_problem() below: a string of at most PROFILE_NAME_MAX_CHARS
# characters, counted as it arrives -- before any cleaning (the reason is in
# that function's docstring). The writers:
# PATCH /users/me (UserUpdate, a 422), the Telegram login (it caps at the
# same number), the seed (scripts/seed.py refuses the project). Names
# written before this rule are not migrated: a longer one stays until its
# owner edits it, and the next edit is held to the rule. An empty string
# and one of spaces are accepted as before -- the rule is about length and
# type, the onboarding step already reads them as "no name".
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

    two_factor_enabled (TASK-38): extracted from credentials.totp.enabled
    via User.two_factor_enabled -- same from_attributes mechanism as
    `email`. Lets any UserResponse consumer (Settings screens in
    particular, see components/shared/TwoFactorSection.vue) know
    whether 2FA is currently on without a dedicated status endpoint.

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
    two_factor_enabled: bool = Field(
        default=False, description="Whether TOTP 2FA is currently active"
    )
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


# The rule above. 100 is what the Telegram login has always kept.
PROFILE_NAME_KEYS = ("first_name", "last_name")
PROFILE_NAME_MAX_CHARS = 100


def clean_profile_text(value: object, limit: int) -> str | None:
    """A profile text from Telegram: printable characters only, trimmed, capped."""
    if not isinstance(value, str):
        return None
    cleaned = "".join(ch for ch in value if ch.isprintable()).strip()
    return cleaned[:limit] or None


def profile_name_problem(key: str, value: object) -> str | None:
    """Why `value` cannot be profile.<key> (one of PROFILE_NAME_KEYS), or None.

    THE LENGTH IS THE RAW ONE, counted before any cleaning (owner ruling,
    H43). The value is stored as it arrives; measured after cleaning, 100
    visible characters could carry a tail of unprintable ones of any length
    (only nginx's 100M body limit would stop it), and that tail reaches the
    e-mail letters whose length comms limits. An empty string and a string
    of spaces within the 100 pass, as before.
    """
    if not isinstance(value, str):
        return f"profile.{key} must be a string"
    if len(value) > PROFILE_NAME_MAX_CHARS:
        return f"profile.{key} is longer than {PROFILE_NAME_MAX_CHARS} characters"
    return None


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

    @field_validator("profile")
    @classmethod
    def _names_follow_the_rule(
        cls, value: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """The names in the profile (see the module header): a 422."""
        if value is None:
            return value
        for key in PROFILE_NAME_KEYS:
            if key in value:
                problem = profile_name_problem(key, value[key])
                if problem is not None:
                    raise ValueError(problem)
        return value


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


class AttachEmailRequest(BaseModel):
    """POST /api/v1/users/me/email -- an account without an e-mail adds one."""

    email: EmailStr = Field(..., description="E-mail address to add")


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
# Self-deactivation (TASK-38)
# ---------------------------------------------------------------------------


class DeactivateAccountRequest(BaseModel):
    """POST /api/v1/users/me/deactivate -- request body.

    current_password confirms a destructive-feeling (though reversible
    -- see users/service.py module note) action, the same re-auth
    pattern _require_current_password enforces for the 2FA endpoints.
    """

    current_password: str = Field(..., min_length=1)
