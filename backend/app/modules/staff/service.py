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
from app.modules.auth.service import delete_all_sessions
from app.modules.staff.avatar_service import close_all_avatar_sessions
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS, is_admin
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
        if "uq_staff_profiles_user_id" in str(exc.orig):
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

    # Imported HERE, not at module scope: support/dependencies.py asks
    # this module who the staff are (get_staff_profile,
    # get_effective_permissions), so a top-level import back into
    # support closes a cycle and breaks the app at startup. The one-way
    # dependency stays support -> staff; this call is the one place the
    # arrow points back, and it points from inside a function.
    from app.modules.support.service import emit_support_membership

    # T-67: a new staff member joins the support section's roster. In
    # the SAME transaction as the promotion -- a profile that exists
    # without its membership event would silently not serve the queue,
    # and the two facts have no reason to be able to disagree.
    await emit_support_membership(session, user_id=target_user_id)

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


async def _active_admin_user_ids(session: AsyncSession) -> list[UUID]:
    """User ids of every ACTIVE staff member who counts as an admin.

    Computed rather than stored: "admin" is not a role in this product,
    it is the state of having every permission key true (design document
    3.10), so the only honest way to count admins is to resolve each
    active profile's effective matrix.
    """
    stmt = select(StaffProfile).where(StaffProfile.is_active.is_(True))
    result = await session.execute(stmt)
    return [
        profile.user_id
        for profile in result.scalars().all()
        if is_admin(get_effective_permissions(profile))
    ]


async def deactivate_staff(
    staff_profile_id: UUID,
    admin: User,
    session: AsyncSession,
) -> StaffProfile:
    """Take a staff member off duty. Admin only.

    Deactivates the PROFILE. The user stays a user and keeps their
    history; every reference to them from the audit log still resolves,
    which is why this is a flag and not a delete. Reversible by design:
    nothing here destroys anything a return would have to rebuild.

    THREE THINGS HAPPEN, NOT ONE, and the order below is the order they
    must happen in:

      1. the flag flips, so the staff dependency stops letting them in;
      2. every avatar session they hold is closed -- see
         close_all_avatar_sessions for why delete_all_sessions cannot do
         this;
      3. comms is told they no longer serve the support section, through
         the outbox, in THIS transaction;
      4. the audit record;
      5. and only then their Redis sessions are killed.

    Redis is last because it is the only step that cannot be rolled
    back. Killing sessions first and then failing on the audit write
    would throw out a person who, after the rollback, is still a staff
    member. If Redis itself is unreachable, delete_all_sessions raises,
    this transaction rolls back, and the person remains staff with their
    sessions intact -- the same choice block_user makes, and it is a
    choice: better not removed at all than removed halfway. Retry when
    Redis is back.

    # KNOWN CEILING (a deactivated staff member cannot be blocked;
    # acknowledged by design):
    #   1. Mechanics: this deactivates the PROFILE and deliberately
    #      leaves User.role as STAFF. block_user (staff/admin_service)
    #      refuses on exactly that field -- "Cannot block staff user" --
    #      so a person removed from staff can no longer be blocked as an
    #      ordinary user either. They keep no staff access (the
    #      dependency checks is_active) and no support queue (the roster
    #      event below), but if they later abuse the product as a
    #      customer, the block endpoint will refuse to touch them.
    #   2. Status: acknowledged by design.
    #   3. Backlog ref: registered by the owner at the T-80 delivery as
    #      a separate task -- teaching block_user to key on an ACTIVE
    #      staff profile instead of on the role.
    #   4. Promotion trigger: the first attempt to block a deactivated
    #      ex-staff member, or any change to what block_user keys on.
    #   5. Agreed fix: block_user checks for an active StaffProfile
    #      rather than User.role, so a serving staff member stays
    #      protected and a removed one does not.
    #   6. Rejected: flipping User.role here. It would make blocking
    #      work today, and it would also strip the role from every
    #      historical read of who did what -- which is the reason
    #      deactivation was chosen over demotion in the first place. Also
    #      rejected: widening block_user inside this delivery, because
    #      that changes the meaning of an existing endpoint and deserves
    #      its own gate rather than a rider on this one.

    Args:
        staff_profile_id: The profile to deactivate.
        admin: The acting staff member (already verified as admin).
        session: Database session.

    Returns:
        The deactivated profile.

    Raises:
        NotFoundError: No such staff profile.
        ConflictError: The profile is already inactive.
        BadRequestError: Deactivating yourself, or the last admin.
    """
    stmt = select(StaffProfile).where(StaffProfile.id == staff_profile_id)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()

    if profile is None:
        raise NotFoundError("Staff profile not found")

    if not profile.is_active:
        # 409 rather than a quiet success: this action writes an audit
        # record, and a second "removed" line in the journal for a
        # removal that did not happen is a lie told to whoever reads it
        # later.
        raise ConflictError(
            "This staff member is already deactivated",
            code="staff_already_inactive",
        )

    if profile.user_id == admin.id:
        raise BadRequestError(
            "You cannot deactivate your own staff profile",
            code="staff_self_deactivation",
        )

    admin_ids = await _active_admin_user_ids(session)
    if profile.user_id in admin_ids and len(admin_ids) == 1:
        # Not a courtesy check. Promoting staff and granting permissions
        # both sit behind _require_admin, so the moment the last admin
        # is gone there is nobody left who can hand admin back -- the
        # permission matrix becomes unreachable from inside the product.
        raise BadRequestError(
            "This is the last active admin: deactivating them would "
            "leave nobody able to grant staff permissions",
            code="staff_last_admin",
        )

    profile.is_active = False
    await session.flush()

    closed_avatars = await close_all_avatar_sessions(profile.user_id, session)

    # Imported inside the function, same as in create_staff and for the
    # same reason: support/dependencies.py asks this module who the
    # staff are, so a module-level import back into support closes a
    # cycle and breaks the app at startup.
    from app.modules.support.service import emit_support_membership

    # The roster event rides this transaction: a person deactivated here
    # while comms still had them serving the section would be off duty
    # for us and on duty for the service.
    await emit_support_membership(
        session, user_id=profile.user_id, member=False
    )

    await record_audit(
        session=session,
        event="staff.deactivated",
        actor_id=admin.id,
        actor_type="staff",
        target_type="staff_profile",
        target_id=profile.id,
        data={
            "target_user_id": str(profile.user_id),
            "avatar_sessions_closed": [str(sid) for sid in closed_avatars],
        },
    )

    killed = await delete_all_sessions(profile.user_id)

    logger.info(
        "staff_deactivated",
        staff_profile_id=str(profile.id),
        target_user_id=str(profile.user_id),
        admin_id=str(admin.id),
        sessions_killed=killed,
        avatar_sessions_closed=len(closed_avatars),
    )

    return profile
