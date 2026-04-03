# =============================================================================
# CBSHOME Backend -- Staff Router (Sprint 3.1)
# =============================================================================
#
# Staff management endpoints.
#
# ENDPOINTS:
#   POST  /api/v1/staff/users                    -- Create staff user
#   GET   /api/v1/staff/users                    -- List staff members
#   PATCH /api/v1/staff/users/{user_id}/permissions -- Update permissions
#
# AUTH:
#   All endpoints require get_current_staff (role=staff + StaffProfile
#   exists + is_active). No specific permission check for these endpoints
#   -- any active staff can manage other staff members.
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
from app.modules.auth.dependencies import get_current_staff
from app.modules.staff.schemas import (
    PermissionsUpdateRequest,
    StaffCreateRequest,
    StaffResponse,
)
from app.modules.staff.service import (
    create_staff,
    list_staff,
    resolve_permissions,
    update_permissions,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


@router.post(
    "/users",
    response_model=StaffResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_staff_user(
    body: StaffCreateRequest,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> StaffResponse:
    """Create a new user with role=staff and a StaffProfile."""
    user, profile = await create_staff(body, staff.id, session)

    email = None
    if user.credentials and "email" in user.credentials:
        email = user.credentials["email"].get("email")

    return StaffResponse(
        id=user.id,
        email=email,
        role=user.role,
        is_active=user.is_active and profile.is_active,
        staff_profile_id=profile.id,
        permissions=resolve_permissions(profile),
        created_at=user.created_at,
    )


@router.get(
    "/users",
    response_model=list[StaffResponse],
)
async def list_staff_users(
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_reader),
) -> list[StaffResponse]:
    """List all staff members with resolved permissions."""
    items = await list_staff(session)
    return [StaffResponse(**item) for item in items]


@router.patch(
    "/users/{user_id}/permissions",
    response_model=StaffResponse,
)
async def update_staff_permissions(
    user_id: UUID,
    body: PermissionsUpdateRequest,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> StaffResponse:
    """Update permission overrides for a staff member."""
    profile = await update_permissions(user_id, body, staff.id, session)

    # Load the user for response construction.
    from sqlalchemy import select

    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one()

    email = None
    if user.credentials and "email" in user.credentials:
        email = user.credentials["email"].get("email")

    return StaffResponse(
        id=user.id,
        email=email,
        role=user.role,
        is_active=user.is_active and profile.is_active,
        staff_profile_id=profile.id,
        permissions=resolve_permissions(profile),
        created_at=user.created_at,
    )
