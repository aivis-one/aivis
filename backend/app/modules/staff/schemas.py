# =============================================================================
# CBSHOME Backend -- Staff Schemas (Sprint 3.1)
# =============================================================================
#
# Pydantic models for staff management endpoints.
#
# StaffCreateRequest:       create a new staff user (email + password)
# StaffResponse:            staff member info with resolved permissions
# PermissionsUpdateRequest: update staff permission overrides
#
# PERMISSION RESOLUTION:
#   StaffResponse.permissions contains the *resolved* permission dict:
#   defaults merged with per-staff overrides from StaffProfile.permissions.
#   The client always sees the effective permissions, never raw overrides.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import VALID_STAFF_PERMISSIONS


class StaffCreateRequest(BaseModel):
    """Create a new user with role=staff + StaffProfile."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    permissions: dict[str, bool] | None = Field(
        default=None,
        description="Permission overrides. Omitted keys use defaults.",
    )

    @field_validator("permissions")
    @classmethod
    def validate_permission_keys(
        cls, v: dict[str, bool] | None,
    ) -> dict[str, bool] | None:
        """Reject unknown permission keys."""
        if v is None:
            return v
        unknown = set(v.keys()) - VALID_STAFF_PERMISSIONS
        if unknown:
            raise ValueError(
                f"Unknown permissions: {sorted(unknown)}. "
                f"Valid: {sorted(VALID_STAFF_PERMISSIONS)}"
            )
        return v


class PermissionsUpdateRequest(BaseModel):
    """Update permission overrides for a staff member."""

    permissions: dict[str, bool] = Field(
        ...,
        description="Permission overrides to set. Only provided keys are changed.",
    )

    @field_validator("permissions")
    @classmethod
    def validate_permission_keys(
        cls, v: dict[str, bool],
    ) -> dict[str, bool]:
        """Reject unknown permission keys."""
        unknown = set(v.keys()) - VALID_STAFF_PERMISSIONS
        if unknown:
            raise ValueError(
                f"Unknown permissions: {sorted(unknown)}. "
                f"Valid: {sorted(VALID_STAFF_PERMISSIONS)}"
            )
        return v


class StaffResponse(BaseModel):
    """Staff member representation in API responses.

    permissions: resolved (defaults + overrides), not raw JSONB.
    email: extracted from credentials JSONB for admin convenience.
    """

    id: UUID
    email: str | None = None
    role: str
    is_active: bool
    staff_profile_id: UUID
    permissions: dict[str, bool]
    created_at: datetime

    model_config = {"from_attributes": True}
