# =============================================================================
# AIVIS.ONE Backend -- Admin Schemas (Sprint 3.3, G5 fix,
#                                    iter 2.7 A5 KYC-in-detail extension,
#                                    H17 P-85 queue removal)
# =============================================================================
#
# SCHEMAS:
#   UserListItem            -- unified user list (with optional staff_profile)
#   UserListResponse        -- paginated list wrapper
#   UserDetailResponse      -- full user detail for staff view
#   DashboardStatsResponse  -- platform-wide statistics
#   KYCApplicationSummary   -- compact KYCApplication for the detail history
#                              (iter 2.7 A5).
#   BlockRequest            -- PATCH /staff/users/{id}/block
#   KYCDecisionRequest      -- staff KYC approve / reject / revoke
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
# H17 P-85 REMOVES KYCQueueItem, GET /staff/kyc/queue AND kyc_queue().
#   The paragraph this replaces called the endpoint "a stable API
#   surface kept for completeness" with "the rows are bounded" -- true
#   only while the table stayed empty, and an un-paginated SELECT *
#   waiting to stop being true. Confirmed before removal: nothing in
#   the frontend has called it since iter 2.7 A2 (fetchKYCQueue's only
#   reference in frontend/src was its own declaration), and the actual
#   queue staff use is /staff/users?kyc_status=submitted -- already
#   paginated, already the address StaffDashboardView's "KYC queue"
#   stat card links to (see the comment on goKyc() there). Keeping an
#   un-paginated SELECT around for a caller that does not exist was
#   the tracked debt TD-KYC-QUEUE-ENDPOINT
#   (AIVIS-Refactor-Investor-Market-And-Staff.md); this pass closes it
#   by deleting the dead surface rather than paginating it.
# =============================================================================

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    Carries no user_id / email / name of its own: this row is always
    nested inside a per-user response (UserDetailResponse's
    kyc_applications_history), so repeating the parent's identity
    fields here would duplicate them for a reader who already has
    them from the object this list sits inside.
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


class KYCDecisionRequest(BaseModel):
    """Request body for any staff KYC decision. The reason is required.

    ONE SCHEMA FOR APPROVE, REJECT AND REVOKE, and the reason is
    mandatory on all three (H10 P-43). It used to be optional and
    reject-only, which left an approval with no record of why it was
    given -- the one decision that opens the whole product to an
    account. min_length plus the strip validator refuse the three forms
    of nothing: absent, empty, and whitespace.

    Stored in the audit log and nowhere else: a column on
    KYCApplication would be a second copy of the same fact.
    """

    reason: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Why this decision was made (stored in audit log)",
    )

    @field_validator("reason")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason must not be blank")
        return stripped
