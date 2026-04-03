# =============================================================================
# CBSHOME Backend -- Staff Service (Sprint 3.1)
# =============================================================================
#
# Business logic for staff management.
#
# FUNCTIONS:
#   create_staff()         -- create User (role=staff) + StaffProfile
#   update_permissions()   -- merge permission overrides into StaffProfile
#   list_staff()           -- all staff members with resolved permissions
#   resolve_permissions()  -- merge defaults + overrides into effective dict
#
# RULES:
#   - P-01: no commit/rollback -- caller manages transaction
#   - P-05: IntegrityError -> begin_nested() savepoint
#   - JSONB mutations via set_jsonb() only
#   - Audit every significant operation
#
# PASSWORD HASHING:
#   Reuses hash_password() from auth.service (argon2id).
#   Does NOT create a Redis session -- new staff logs in separately.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.constants import DEFAULT_STAFF_PERMISSIONS, VALID_STAFF_PERMISSIONS
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.auth.service import hash_password
from app.modules.staff.models import StaffProfile
from app.modules.staff.schemas import PermissionsUpdateRequest, StaffCreateRequest
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


def resolve_permissions(profile: StaffProfile) -> dict[str, bool]:
    """Merge default permissions with per-staff overrides.

    Resolution order: profile.permissions[key] ?? DEFAULT[key].
    Returns a complete dict with all known permission keys.
    """
    resolved = dict(DEFAULT_STAFF_PERMISSIONS)
    for key, value in profile.permissions.items():
        if key in VALID_STAFF_PERMISSIONS:
            resolved[key] = bool(value)
    return resolved


async def create_staff(
    body: StaffCreateRequest,
    actor_id: UUID,
    session: AsyncSession,
) -> tuple[User, StaffProfile]:
    """Create a new user with role=staff and a StaffProfile.

    Args:
        body: email, password, optional permission overrides.
        actor_id: UUID of the staff member performing this action.
        session: active DB session (caller manages commit).

    Returns:
        (User, StaffProfile) tuple.

    Raises:
        ConflictError: if email already exists.
    """
    password_hash = hash_password(body.password)

    credentials = {
        "email": {
            "email": body.email,
            "password_hash": password_hash,
            "verified": True,
            "verified_at": None,
        },
    }

    user = User(
        role=UserRole.STAFF,
        credentials=credentials,
    )

    # P-05: session.add + flush inside begin_nested so that
    # IntegrityError on duplicate email is caught within the
    # savepoint, not on the outer transaction.
    async with session.begin_nested():
        session.add(user)
        try:
            await session.flush()
        except IntegrityError as exc:
            if "ix_users_email" in str(exc.orig):
                raise ConflictError("Email already registered") from exc
            raise

    # Create StaffProfile with optional permission overrides.
    profile = StaffProfile(
        user_id=user.id,
        permissions=body.permissions or {},
    )
    session.add(profile)
    await session.flush()

    await record_audit(
        session=session,
        event="user.registered",
        actor_id=actor_id,
        actor_type="staff",
        target_type="user",
        target_id=user.id,
        data={"auth_method": "staff_created", "role": "staff"},
    )

    logger.info(
        "staff_user_created",
        user_id=str(user.id),
        created_by=str(actor_id),
    )

    return user, profile


async def update_permissions(
    user_id: UUID,
    body: PermissionsUpdateRequest,
    actor_id: UUID,
    session: AsyncSession,
) -> StaffProfile:
    """Update permission overrides for a staff member.

    Merges incoming keys with existing overrides (shallow merge).
    Keys not in the request body are left unchanged.

    Args:
        user_id: target staff user's UUID.
        body: dict of permission key -> bool to set.
        actor_id: UUID of the staff member performing this action.
        session: active DB session (caller manages commit).

    Returns:
        Updated StaffProfile.

    Raises:
        NotFoundError: if user_id has no StaffProfile.
    """
    stmt = select(StaffProfile).where(StaffProfile.user_id == user_id)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise NotFoundError("Staff profile not found")

    # Shallow merge: update only provided keys.
    merged = dict(profile.permissions)
    merged.update(body.permissions)
    profile.set_jsonb("permissions", merged)

    await session.flush()
    await session.refresh(profile)

    await record_audit(
        session=session,
        event="staff.permissions_changed",
        actor_id=actor_id,
        actor_type="staff",
        target_type="staff_profile",
        target_id=profile.id,
        data={
            "user_id": str(user_id),
            "changed_keys": sorted(body.permissions.keys()),
        },
    )

    logger.info(
        "staff_permissions_updated",
        target_user_id=str(user_id),
        changed_by=str(actor_id),
        keys=sorted(body.permissions.keys()),
    )

    return profile


async def list_staff(session: AsyncSession) -> list[dict]:
    """List all staff members with resolved permissions.

    Returns a list of dicts ready for StaffResponse serialization.
    Platform user is excluded (role != staff wouldn't match anyway).
    """
    stmt = (
        select(User, StaffProfile)
        .join(StaffProfile, StaffProfile.user_id == User.id)
        .where(User.role == UserRole.STAFF)
        .order_by(User.created_at)
    )
    result = await session.execute(stmt)
    rows = result.all()

    items = []
    for user, profile in rows:
        email = None
        if user.credentials and "email" in user.credentials:
            email = user.credentials["email"].get("email")

        items.append({
            "id": user.id,
            "email": email,
            "role": user.role,
            "is_active": user.is_active and profile.is_active,
            "staff_profile_id": profile.id,
            "permissions": resolve_permissions(profile),
            "created_at": user.created_at,
        })

    return items


async def get_staff_profile_by_user_id(
    user_id: UUID,
    session: AsyncSession,
) -> StaffProfile | None:
    """Load StaffProfile by user_id. Returns None if not found."""
    stmt = select(StaffProfile).where(StaffProfile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
