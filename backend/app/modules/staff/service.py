# =============================================================================
# AIVIS.ONE Backend -- Staff Service (Sprint 3.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_staff()          -- promote existing user to staff role
#   update_permissions()    -- update staff permission matrix
#   get_staff_profile()     -- load StaffProfile by user_id
#   get_effective_permissions() -- merge config defaults with overrides
#
# USER MANAGEMENT (Sprint 3.3):
#   list_users, get_user_detail, block_user moved to admin_service.py.
#
# ADMIN CHECK:
#   Admin = staff with ALL permissions True. Checked via is_admin().
#   Only admin can create staff and update permissions.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
#
# JSONB RULE:
#   Permissions updated via set_jsonb() (JSONBMixin). Never direct assign.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS
from app.modules.staff.models import StaffProfile
from app.modules.staff.schemas import UpdatePermissionsRequest
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


def get_effective_permissions(profile: StaffProfile) -> dict[str, bool]:
    """Merge config defaults with per-staff overrides.

    StaffProfile.permissions stores only overrides (may be empty {}).
    Effective = defaults merged with overrides.
    """
    effective = dict(DEFAULT_STAFF_PERMISSIONS)
    if profile.permissions:
        effective.update(profile.permissions)
    return effective


async def get_staff_profile(
    user_id: UUID,
    session: AsyncSession,
) -> StaffProfile | None:
    """Load StaffProfile by user_id. Returns None if not found."""
    stmt = select(StaffProfile).where(StaffProfile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_staff(
    target_user_id: UUID,
    admin: User,
    session: AsyncSession,
) -> StaffProfile:
    """Promote an existing user to staff role.

    Creates StaffProfile with default permissions and changes user role.
    Only admin (all permissions True) can call this.

    Raises:
        NotFoundError: If target user not found.
        BadRequestError: If target is platform user.
        ConflictError: If user is already staff.
    """
    # Load target user.
    stmt = select(User).where(User.id == target_user_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        raise NotFoundError("User not found")

    if target.role == UserRole.PLATFORM:
        raise BadRequestError("Cannot promote platform user to staff")

    if target.role == UserRole.STAFF:
        raise ConflictError("User is already staff")

    # Change role.
    target.role = UserRole.STAFF

    # Create StaffProfile with default permissions.
    profile = StaffProfile(
        user_id=target_user_id,
        permissions=dict(DEFAULT_STAFF_PERMISSIONS),
        is_active=True,
    )
    session.add(profile)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "staff_profiles_user_id_key" in str(exc.orig):
            raise ConflictError("Staff profile already exists")
        raise

    await session.refresh(profile)

    # Audit.
    await record_audit(
        session=session,
        event="staff.created",
        actor_id=admin.id,
        actor_type="staff",
        target_type="user",
        target_id=target_user_id,
        data={"permissions": dict(DEFAULT_STAFF_PERMISSIONS)},
    )

    logger.info(
        "staff_created",
        target_user_id=str(target_user_id),
        admin_id=str(admin.id),
    )

    return profile


async def update_permissions(
    staff_profile_id: UUID,
    body: UpdatePermissionsRequest,
    admin: User,
    session: AsyncSession,
) -> StaffProfile:
    """Update staff permission matrix (partial update).

    Only admin can call this. Only provided fields are updated.

    Raises:
        NotFoundError: If staff profile not found.
    """
    stmt = select(StaffProfile).where(StaffProfile.id == staff_profile_id)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()

    if profile is None:
        raise NotFoundError("Staff profile not found")

    # Build updated permissions: start from current, apply changes.
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        return profile

    current = dict(profile.permissions) if profile.permissions else {}
    new_permissions = {**current, **updates}

    # set_jsonb for safe JSONB mutation.
    profile.set_jsonb("permissions", new_permissions)
    await session.flush()
    await session.refresh(profile)

    # Audit.
    await record_audit(
        session=session,
        event="staff.permissions_updated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="staff_profile",
        target_id=profile.id,
        data={"changes": updates, "result": new_permissions},
    )

    logger.info(
        "staff_permissions_updated",
        staff_profile_id=str(profile.id),
        admin_id=str(admin.id),
        changes=updates,
    )

    return profile
