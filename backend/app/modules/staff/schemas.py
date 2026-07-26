# =============================================================================
# AIVIS.ONE Backend -- Staff Schemas (Sprint 3.1, updated Sprint 4.1,
#                                    iter 2.7 A6 content_manage sync)
# =============================================================================
#
# REQUEST/RESPONSE SCHEMAS:
#   CreateStaffRequest        -- POST /staff/users {user_id}
#   UpdatePermissionsRequest  -- PATCH /staff/users/{id}/permissions
#   StaffProfileResponse      -- response for all staff endpoints
#   StaffListResponse         -- list item (profile + user info)
#
# Sprint 4.1:
#   Added company_manage to UpdatePermissionsRequest.
#
# iter 2.7 A6 content_manage sync:
#   Sprint 9.1 added `content_manage` to DEFAULT_STAFF_PERMISSIONS
#   (staff/constants.py) but never to this schema. Because
#   UpdatePermissionsRequest has `extra="forbid"`, the omission
#   silently meant that PATCH /staff/users/{id}/permissions could
#   not toggle `content_manage` -- every request carrying it would
#   fail with 422. Reads via the effective dict on /users/me kept
#   working (staff/service.get_effective_permissions reads from
#   DEFAULT_STAFF_PERMISSIONS, which already had the key), so the
#   feature flag was functional but not adjustable per-staff
#   through the admin UI. This commit closes the drift.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateStaffRequest(BaseModel):
    """Request to promote an existing user to staff role."""

    user_id: UUID


class UpdatePermissionsRequest(BaseModel):
    """Request to update staff permissions (partial update).

    Only provided keys are updated; missing keys retain current values.
    """

    model_config = ConfigDict(extra="forbid")

    avatar_mode: bool | None = None
    kyc_approve: bool | None = None
    payment_review: bool | None = None
    user_block: bool | None = None
    financial_operations: bool | None = None
    agent_application_review: bool | None = None
    translation_edit: bool | None = None
    company_manage: bool | None = None
    content_manage: bool | None = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class StaffProfileResponse(BaseModel):
    """Staff profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    permissions: dict[str, bool]
    is_active: bool
    created_at: datetime


class StaffListItem(BaseModel):
    """Staff list item -- profile + basic user info."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    permissions: dict[str, bool]
    is_active: bool
    created_at: datetime
    # User fields (populated in service)
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
