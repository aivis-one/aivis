# =============================================================================
# CBSHOME Backend -- Admin Schemas (Sprint 3.3)
# =============================================================================
#
# SCHEMAS:
#   UserListItem         -- unified user list (with optional staff_profile)
#   UserListResponse     -- paginated list wrapper
#   UserDetailResponse   -- full user detail for staff view
#   DashboardStatsResponse -- platform-wide statistics
#   KYCQueueItem         -- pending KYC application with user info
#   BlockRequest         -- PATCH /staff/users/{id}/block
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.staff.schemas import StaffProfileResponse


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


class UserListItem(BaseModel):
    """Unified user list item -- any role, optional staff_profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    is_active: bool
    kyc_status: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    created_at: datetime
    staff_profile: StaffProfileResponse | None = None


class UserListResponse(BaseModel):
    """Paginated user list."""

    items: list[UserListItem]
    total: int
    page: int
    per_page: int


class UserDetailResponse(BaseModel):
    """Full user detail for staff view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    is_active: bool
    onboarding_step: str
    kyc_status: str
    profile: dict[str, Any]
    language: str
    created_at: datetime
    updated_at: datetime | None = None
    email: str | None = None
    staff_profile: StaffProfileResponse | None = None


class BlockRequest(BaseModel):
    """Request to block a user."""

    reason: str | None = None


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class DashboardStatsResponse(BaseModel):
    """Platform-wide statistics for staff dashboard."""

    total_users: int
    users_by_role: dict[str, int]
    pending_kyc_count: int
    active_avatar_sessions: int


# ---------------------------------------------------------------------------
# KYC queue
# ---------------------------------------------------------------------------


class KYCQueueItem(BaseModel):
    """Pending KYC application with basic user info."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
