# =============================================================================
# CBSHOME Backend -- Staff Router (Sprint 3.1)
# =============================================================================
#
# ENDPOINTS:
#   POST  /api/v1/staff/users                  -- promote user to staff (admin only)
#   PATCH /api/v1/staff/users/{id}/permissions  -- update permissions (admin only)
#   GET   /api/v1/staff/users                   -- list all staff (any staff)
#
# AUTH:
#   All endpoints require get_current_staff (role=staff + StaffProfile loaded).
#   POST and PATCH additionally require admin (all permissions True).
#   get_current_staff returns (User, StaffProfile) -- no second DB query needed.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import get_current_staff
from app.modules.staff.constants import is_admin
from app.modules.staff.models import StaffProfile
from app.modules.staff.schemas import (
    CreateStaffRequest,
    StaffListItem,
    StaffProfileResponse,
    UpdatePermissionsRequest,
)
from app.modules.staff.service import (
    create_staff,
    get_effective_permissions,
    list_staff,
    update_permissions,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/users", tags=["staff-users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_admin(profile: StaffProfile) -> None:
    """Check that the staff member is admin (all permissions True).

    Uses the StaffProfile already loaded by get_current_staff dependency.
    No extra DB query needed.

    Raises ForbiddenError if not admin.
    """
    effective = get_effective_permissions(profile)
    if not is_admin(effective):
        raise ForbiddenError("Admin access required")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=StaffProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def staff_create(
    body: CreateStaffRequest,
    staff_data: tuple[User, StaffProfile] = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> StaffProfileResponse:
    """Promote an existing user to staff role. Admin only."""
    staff, staff_profile = staff_data
    _require_admin(staff_profile)
    profile = await create_staff(body.user_id, staff, session)
    return StaffProfileResponse.model_validate(profile)


@router.patch(
    "/{staff_profile_id}/permissions",
    response_model=StaffProfileResponse,
)
async def staff_update_permissions(
    staff_profile_id: UUID,
    body: UpdatePermissionsRequest,
    staff_data: tuple[User, StaffProfile] = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> StaffProfileResponse:
    """Update staff permissions. Admin only."""
    staff, staff_profile = staff_data
    _require_admin(staff_profile)
    profile = await update_permissions(staff_profile_id, body, staff, session)

    # Return with effective permissions (defaults merged).
    response = StaffProfileResponse.model_validate(profile)
    response.permissions = get_effective_permissions(profile)
    return response


@router.get(
    "",
    response_model=list[StaffListItem],
)
async def staff_list(
    staff_data: tuple[User, StaffProfile] = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_reader),
) -> list[StaffListItem]:
    """List all staff profiles with user info. Any staff can view."""
    return await list_staff(session)
