# =============================================================================
# AIVIS.ONE Backend -- the first admin (H30 P-118)
# =============================================================================
#
# THE ONE BYPASS. create_staff(target_user_id, admin, session) promotes an
# existing user and takes an admin as the actor. On a box with no admin
# there is nobody to be that actor, so the first admin cannot be made
# through that path -- chicken and egg, not an oversight. This module is
# the only place the promotion is written WITHOUT an actor:
#
#   write_admin_promotion() -- the three writes create_staff makes
#       internally (role, StaffProfile, membership event), with every
#       permission True. Used by both callers below; there is no second
#       copy of these writes anywhere.
#   find_any_admin()        -- "does this box already have an admin".
#   bootstrap_first_admin() -- the production path: `aivis bootstrap-admin
#       <email>` (scripts/bootstrap_admin.py). Promotes an ALREADY
#       registered, verified user and creates nothing else -- no people,
#       no companies, no passwords. Every refusal leaves the database
#       untouched.
#
# scripts/seed.py::ensure_admin is the other caller. It keeps its own
# decisions (an existing admin is reused, an existing profile is left
# alone) and calls write_admin_promotion for the writes.
#
# Every later staff member goes through create_staff with an admin as the
# actor; once an admin exists, bootstrap_first_admin refuses for good.
# =============================================================================

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.modules.staff.constants import VALID_PERMISSION_KEYS, is_admin
from app.modules.staff.models import StaffProfile
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


class BootstrapRefusedError(Exception):
    """bootstrap_first_admin refused; the message says why, for an operator."""


async def find_any_admin(session: AsyncSession) -> User | None:
    """The first active admin on this box, or None.

    is_admin() is a permission-set predicate, not a column, so this reads
    the profiles rather than filtering in SQL.
    """
    stmt = (
        select(StaffProfile, User)
        .join(User, User.id == StaffProfile.user_id)
        .where(StaffProfile.is_active.is_(True))
    )
    for staff_profile, user in (await session.execute(stmt)).all():
        if is_admin(staff_profile.permissions):
            return user
    return None


async def write_admin_promotion(session: AsyncSession, user: User) -> StaffProfile:
    """Make `user` an admin: the three writes, and nothing else.

    The role, the StaffProfile row with every permission True, and the
    support membership event -- the same three create_staff makes, in the
    same transaction, because a profile without its membership event would
    silently not serve the support queue.

    The caller has already decided this person may be promoted and has no
    staff profile (staff_profiles.user_id is UNIQUE). The comms recipient
    is not touched: the user came through registration, and the snapshot
    does not carry the role.
    """
    # Imported here, not at module scope -- the same cycle create_staff
    # documents: support/dependencies.py imports the staff package.
    from app.modules.support.service import emit_support_membership

    user.role = UserRole.STAFF
    profile = StaffProfile(
        user_id=user.id,
        permissions={key: True for key in VALID_PERMISSION_KEYS},
        is_active=True,
    )
    session.add(profile)
    await session.flush()
    await emit_support_membership(session, user_id=user.id)
    await session.refresh(user)
    return profile


async def bootstrap_first_admin(session: AsyncSession, email: str) -> User:
    """Promote the registered user with this address to the first admin.

    Refusals, each with nothing written (the caller rolls back):
      - the box already has an active admin -- unconditional: from then on
        staff is appointed through the interface;
      - nobody is registered with this address (compared lower-cased and
        stripped, as registration stores it);
      - the account is blocked;
      - the address is not verified;
      - the person already has a staff profile, active or not, with any
        permissions -- appointing staff is the interface's job.

    Writes an audit row staff.bootstrapped with the system as the actor:
    there is no admin to be one, and the first admin of a box is exactly
    the event an audit trail exists for.
    """
    existing_admin = await find_any_admin(session)
    if existing_admin is not None:
        raise BootstrapRefusedError(
            "This box already has an admin -- appoint staff through the "
            "staff interface instead."
        )

    email_lower = email.strip().lower()
    user = (
        await session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email_lower
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise BootstrapRefusedError(
            f"Nobody is registered with {email_lower} -- register through "
            "the site first, then run this again."
        )

    if not user.is_active:
        raise BootstrapRefusedError(
            f"The account {email_lower} is blocked -- it cannot be made admin."
        )

    if not (user.credentials.get("email") or {}).get("verified"):
        raise BootstrapRefusedError(
            f"The address {email_lower} is not verified -- finish the "
            "registration (the code from the letter) first."
        )

    existing_profile = (
        await session.execute(
            select(StaffProfile.id).where(StaffProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    if existing_profile is not None:
        raise BootstrapRefusedError(
            f"{email_lower} already has a staff profile -- change its "
            "permissions through the staff interface."
        )

    profile = await write_admin_promotion(session, user)

    await record_audit(
        session=session,
        event="staff.bootstrapped",
        actor_id=None,
        actor_type="system",
        target_type="user",
        target_id=user.id,
        data={"permissions": dict(profile.permissions)},
    )

    logger.info("staff_bootstrapped", user_id=str(user.id))
    return user


__all__ = [
    "BootstrapRefusedError",
    "bootstrap_first_admin",
    "find_any_admin",
    "write_admin_promotion",
]
