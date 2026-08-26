# =============================================================================
# AIVIS.ONE Backend -- Staff Router (Sprint 3.1 + 3.3, iter 2.6c B1)
# =============================================================================
#
# ENDPOINTS:
#   POST  /api/v1/staff/users                     -- promote user to staff (admin)
#   PATCH /api/v1/staff/users/{id}/permissions     -- update permissions (admin)
#   GET   /api/v1/staff/users                      -- unified user list
#                                                    (?role=, ?kyc_status=, pagination)
#   GET   /api/v1/staff/users/{id}                 -- user detail
#   PATCH /api/v1/staff/users/{id}/block           -- block user (user_block perm)
#
# AUTH:
#   POST/PATCH permissions: admin only (all permissions True).
#   GET list/detail: any staff.
#   PATCH block: requires user_block permission.
#
# iter 2.6c B1:
#   GET /staff/users gains an optional ?kyc_status= filter so the
#   Staff Platform tab can drive a KYC queue view off the same
#   endpoint instead of issuing a parallel call to /staff/kyc/queue.
#   FastAPI binds the param to the KYCStatus StrEnum -- any value
#   outside {not_started, submitted, approved, rejected} fails at
#   the framework boundary with 422.
#
# iter 2.6c followup (OBS-33-01):
#   ?role= is also bound to a StrEnum (UserRole) so unknown values
#   are rejected with 422 instead of silently returning an empty
#   list. Service layer signature unchanged -- the router unwraps
#   .value before passing through.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import (
    get_current_staff,
    require_staff_permission,
)
from app.modules.staff.admin_schemas import (
    BlockRequest,
    UserDetailResponse,
    UserListResponse,
)
from app.modules.staff.admin_service import (
    block_user,
    get_user_detail,
    list_users,
)
from app.modules.staff.constants import is_admin
from app.modules.staff.schemas import (
    CreateStaffRequest,
    StaffProfileResponse,
    UpdatePermissionsRequest,
)
from app.modules.staff.service import (
    create_staff,
    deactivate_staff,
    get_effective_permissions,
    get_staff_profile,
    update_permissions,
)
from app.modules.users.models import KYCStatus, User, UserRole

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/users", tags=["staff-users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_admin(staff: User, session: AsyncSession) -> None:
    """Check that the current staff member is admin (all permissions True).

    Raises ForbiddenError if not admin.
    """
    profile = await get_staff_profile(staff.id, session)
    if profile is None:
        raise ForbiddenError("Staff profile not found")

    effective = get_effective_permissions(profile)
    if not is_admin(effective):
        raise ForbiddenError("Admin access required")


# ---------------------------------------------------------------------------
# Staff promotion (Sprint 3.1)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=StaffProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def staff_create(
    body: CreateStaffRequest,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> StaffProfileResponse:
    """Promote an existing user to staff role. Admin only."""
    await _require_admin(staff, session)
    profile = await create_staff(body.user_id, staff, session)
    return StaffProfileResponse.model_validate(profile)


@router.post("/{staff_profile_id}/deactivate")
async def deactivate_staff_member(
    staff_profile_id: UUID,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> StaffProfileResponse:
    """Take a staff member off duty. Admin only.

    POST rather than DELETE, and the difference is not cosmetic: the
    profile row stays, with its permissions and its history. DELETE
    would promise removal of a thing this endpoint deliberately keeps.

    Admin only, by the same dependency that guards promotion: granting
    staff and taking it away are one right, and splitting them would
    mean somebody could remove a person they could not restore.
    """
    await _require_admin(staff, session)
    profile = await deactivate_staff(staff_profile_id, staff, session)
    return StaffProfileResponse.model_validate(profile)


@router.patch(
    "/{staff_profile_id}/permissions",
    response_model=StaffProfileResponse,
)
async def staff_update_permissions(
    staff_profile_id: UUID,
    body: UpdatePermissionsRequest,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> StaffProfileResponse:
    """Update staff permissions. Admin only."""
    await _require_admin(staff, session)
    profile = await update_permissions(staff_profile_id, body, staff, session)

    # Return with effective permissions (defaults merged).
    response = StaffProfileResponse.model_validate(profile)
    response.permissions = get_effective_permissions(profile)
    return response


# ---------------------------------------------------------------------------
# User management (Sprint 3.3, +kyc_status filter iter 2.6c B1)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=UserListResponse,
)
async def user_list(
    role: UserRole | None = Query(
        default=None,
        description=(
            "Filter by role: investor, agent, company, staff, or "
            "platform. Unknown values are rejected with 422."
        ),
    ),
    kyc_status: KYCStatus | None = Query(
        default=None,
        description=(
            "Filter by KYC status: not_started, submitted, approved, "
            "or rejected."
        ),
    ),
    search: str | None = Query(
        default=None,
        max_length=255,
        description=(
            "Case-insensitive substring match on email, first_name, or "
            "last_name. Used by the staff user picker (assign-to-company, "
            "avatar mode) to find a target user without knowing their UUID."
        ),
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page"),
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_reader),
) -> UserListResponse:
    """List all users with pagination. Optional ?role= and ?kyc_status= filters.

    Platform user is always excluded. For staff users, includes
    StaffProfile with effective permissions.

    iter 2.6c B1: ?kyc_status= is a typed KYCStatus enum at the
    framework boundary, so unknown values are rejected by FastAPI
    with 422 before reaching the service layer.

    iter 2.6c followup (OBS-33-01): ?role= is now bound to UserRole
    StrEnum too. Previously the param accepted plain str, so any
    garbage value silently produced an empty result set; now FastAPI
    rejects unknown values with 422 at the framework boundary. The
    service still receives a plain str (.value extraction below) so
    no service-layer change is needed.

    Note that filtering by role="platform" returns an empty list:
    the service excludes the platform user from every result via
    `User.role != UserRole.PLATFORM`, and that exclusion is the
    authoritative invariant -- not removed because a caller asked
    for it explicitly.

    ?search= (TASK-30 admin-capability gap): email/first_name/last_name
    live in JSONB (credentials, profile), not plain columns, so this
    matches list_companies' ?search= pattern (ILIKE, metacharacters
    escaped) rather than a column filter.
    """
    return await list_users(
        session,
        role=role.value if role is not None else None,
        kyc_status=kyc_status.value if kyc_status is not None else None,
        search=search,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
)
async def user_detail(
    user_id: UUID,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_reader),
) -> UserDetailResponse:
    """Get full user detail. Platform user is not viewable."""
    return await get_user_detail(user_id, session)


@router.patch(
    "/{user_id}/block",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def user_block(
    user_id: UUID,
    body: BlockRequest,
    staff: User = Depends(require_staff_permission("user_block")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Block a user: deactivate + kill all sessions.

    Only non-staff users can be blocked. Requires user_block permission.
    """
    await block_user(user_id, staff, body.reason, session)
