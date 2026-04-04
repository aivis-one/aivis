# =============================================================================
# CBSHOME Backend -- Staff Service (Sprint 3.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   create_staff()          -- promote existing user to staff role
#   update_permissions()    -- update staff permission matrix
#   list_staff()            -- list all staff profiles with user info
#   get_staff_profile()     -- load StaffProfile by user_id
#   get_effective_permissions() -- merge config defaults with overrides
#
# ADMIN CHECK:
#   Admin = staff with ALL permissions True. Checked via is_admin().
#   Only admin can create staff and update permissions.
#
# LAST-ADMIN GUARD:
#   Cannot remove admin status from the last remaining admin.
#   Prevents lockout scenario where no one can manage staff.
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
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS, is_admin
from app.modules.staff.models import StaffProfile
from app.modules.staff.schemas import StaffListItem, UpdatePermissionsRequest
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


async def _count_admins(session: AsyncSession) -> int:
    """Count staff profiles that have admin-level permissions (all True)."""
    stmt = select(StaffProfile).where(StaffProfile.is_active.is_(True))
    result = await session.execute(stmt)
    profiles = result.scalars().all()

    count = 0
    for profile in profiles:
        effective = get_effective_permissions(profile)
        if is_admin(effective):
            count += 1
    return count


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
    Prevents removing admin status from the last remaining admin.

    Raises:
        NotFoundError: If staff profile not found.
        BadRequestError: If update would remove the last admin.
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

    # Last-admin guard: if this profile is currently admin and the update
    # would make it non-admin, check there's at least one other admin.
    current_effective = get_effective_permissions(profile)
    new_effective = dict(DEFAULT_STAFF_PERMISSIONS)
    new_effective.update(new_permissions)

    if is_admin(current_effective) and not is_admin(new_effective):
        admin_count = await _count_admins(session)
        if admin_count <= 1:
            raise BadRequestError(
                "Cannot remove admin permissions: this is the last admin"
            )

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


async def list_staff(
    session: AsyncSession,
) -> list[StaffListItem]:
    """List all staff profiles with basic user info.

    Returns StaffListItem with email, first_name, last_name from User.
    Platform user is never staff, so no filtering needed.
    """
    stmt = (
        select(StaffProfile, User)
        .join(User, StaffProfile.user_id == User.id)
        .order_by(StaffProfile.created_at.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    items = []
    for profile, user in rows:
        # Extract email and name from User JSONB fields.
        email = None
        if user.credentials and "email" in user.credentials:
            email = user.credentials["email"].get("email")

        first_name = None
        last_name = None
        if user.profile:
            first_name = user.profile.get("first_name")
            last_name = user.profile.get("last_name")

        items.append(StaffListItem(
            id=profile.id,
            user_id=profile.user_id,
            permissions=get_effective_permissions(profile),
            is_active=profile.is_active,
            created_at=profile.created_at,
            email=email,
            first_name=first_name,
            last_name=last_name,
        ))

    return items
