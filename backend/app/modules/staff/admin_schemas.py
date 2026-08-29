# =============================================================================
# AIVIS.ONE Backend -- Admin Schemas (Sprint 3.3, G5 fix,
#                                    iter 2.7 A5 KYC-in-detail extension)
# =============================================================================
#
# SCHEMAS:
#   UserListItem            -- unified user list (with optional staff_profile)
#   UserListResponse        -- paginated list wrapper
#   UserDetailResponse      -- full user detail for staff view
#   DashboardStatsResponse  -- platform-wide statistics
#   KYCQueueItem            -- pending KYC application with user info
#   KYCApplicationSummary   -- compact KYCApplication for the detail history
#                              (iter 2.7 A5).
#   BlockRequest            -- PATCH /staff/users/{id}/block
#   KYCRejectRequest        -- POST /staff/kyc/{id}/reject
#
# iter 2.7 A5 KYC-in-detail extension.
#   StaffUsersView merges the old StaffKYCView Approve/Reject flow into
#   the user detail modal (R1 §3). To approve or reject a single user's
#   pending application without the dedicated queue page, the frontend
#   needs the application id on UserDetailResponse. Adding a single
#   `latest_application_id` would have worked for the simplest case,
#   but R1 §3 also asks for "history of re-submits if present" -- so
#   the same one response carries both:
#
#     latest_application_id      -- UUID of the newest application
#                                   (None if the user has never
#                                   submitted KYC).
#     latest_application_status  -- its status (NOT_STARTED is not
#                                   represented as an application row,
#                                   so it never appears here).
#     kyc_applications_history   -- compact list of up to KYC_HISTORY_LIMIT
#                                   newest applications (NEWEST FIRST),
#                                   enough to render a re-submit timeline.
#
#   The endpoint /staff/kyc/queue stays for the legacy global queue
#   view (none of the frontend reads it any more after iter 2.7 A2,
#   but kept as a stable API surface for completeness; the cost is
#   one SELECT and the rows are bounded).
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.staff.schemas import StaffProfileResponse


# Soft cap on the per-user KYC history list returned by
# get_user_detail. Ten covers every realistic re-submit timeline
# (most users have one or two rows; a fraud-flagged user might have
# four or five). The list is sorted newest-first, so a power user
# with eleven attempts still sees the most recent ten.
KYC_HISTORY_LIMIT = 10


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


class KYCApplicationSummary(BaseModel):
    """Compact KYCApplication row for the user detail history.

    Mirrors the columns the staff detail modal actually renders:
    id (for action endpoints), status (badge color), created_at
    (timeline ordering / submission date), updated_at (when the
    status changed for terminal statuses).

    Distinct from KYCQueueItem -- that one carries denormalized
    user info for the global queue, this one is already nested
    inside a per-user response so user_id / email / name would
    duplicate the parent.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime | None = None


class UserDetailResponse(BaseModel):
    """Full user detail for staff view.

    iter 2.7 A5 additions (kyc-in-detail extension):
      - latest_application_id      : newest KYCApplication.id or None.
      - latest_application_status  : its status, mirroring user.kyc_status
                                     for non-trivial cases (and None for
                                     users who have never submitted).
      - kyc_applications_history   : up to KYC_HISTORY_LIMIT newest rows,
                                     NEWEST FIRST. Empty list if the
                                     user has never submitted.
    """

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

    # iter 2.7 A5: KYC application info for the merged Approve/Reject
    # flow in StaffUsersView's detail modal.
    latest_application_id: UUID | None
    latest_application_status: str | None
    kyc_applications_history: list[KYCApplicationSummary]


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
    frozen_payments_count: int


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


class KYCRejectRequest(BaseModel):
    """Request body for KYC rejection with optional reason."""

    reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Rejection reason (stored in audit log)",
    )
