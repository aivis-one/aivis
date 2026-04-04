# =============================================================================
# CBSHOME Backend -- Auth Dependencies
# =============================================================================
#
# FastAPI dependencies for request authentication.
#
# DEPENDENCY OVERVIEW:
#   get_current_user           -- any authenticated user, read session
#   get_current_user_write     -- any authenticated user, write session
#   get_optional_user          -- optional auth, read session; None if no token
#   get_current_staff          -- staff role + StaffProfile (active) required
#   require_staff_permission() -- factory: staff + specific permission check
#
# TD-029 PATTERN (from VELO):
#   get_current_user_write uses get_db_session instead of get_db_reader.
#   FastAPI caches Depends within a request, so if the router also
#   declares Depends(get_db_session), both receive the SAME session
#   instance -- one DB connection, no merge needed.
#
# PLATFORM USER BLOCK:
#   role=platform is rejected in _load_user_from_request() with 401.
#   Platform user is a system actor, never logs in via API.
#
# STAFF PERMISSION CHECK (Sprint 3.1):
#   get_current_staff verifies: role == staff, StaffProfile exists,
#   StaffProfile.is_active. Does NOT check specific permissions --
#   use require_staff_permission("perm_name") for that.
#
#   require_staff_permission() returns a FastAPI dependency that
#   performs the full staff check PLUS verifies a specific permission
#   against resolved defaults + overrides.
#
# AVATAR CONTEXT (Sprint 3.2):
#   If Redis session contains avatar_session_id, _load_user_from_request
#   binds avatar_session_id and avatar_staff_id to structlog contextvars.
#   This enables:
#     - avatar_guard.py to block restricted operations
#     - record_audit() to auto-fill performed_by / on_behalf_of
#     - Every log line in avatar mode to include avatar_session_id
#
# SINGLE SOURCE:
#   Staff permission constants imported from app.modules.staff.constants
#   (not duplicated in core/constants.py).
# =============================================================================

from typing import Callable
from uuid import UUID

import structlog
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.modules.auth.service import get_session
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS, VALID_PERMISSION_KEYS
from app.modules.staff.models import StaffProfile
from app.modules.users.models import User, UserRole


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header.

    Returns None if header is missing or malformed.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    return token or None


def _parse_user_id(session_data: dict) -> UUID:
    """Parse user_id from Redis session data.

    Returns clean 401 instead of 500 if Redis contains corrupted
    or non-UUID values.
    """
    try:
        return UUID(session_data["user_id"])
    except (KeyError, ValueError, TypeError, AttributeError):
        raise UnauthorizedError("Invalid session data") from None


async def _load_user_from_request(
    request: Request,
    session: AsyncSession,
) -> User:
    """Shared auth logic: token -> Redis -> DB.

    Raises UnauthorizedError or ForbiddenError on failure.
    Used by get_current_user, get_current_user_write, and get_optional_user.

    Sprint 3.2: If session contains avatar_session_id, binds avatar context
    to structlog contextvars for logging, audit, and avatar_guard.
    """
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError("Authorization header required")

    session_data = await get_session(token)
    if not session_data:
        raise UnauthorizedError("Invalid or expired session")

    user_id = _parse_user_id(session_data)
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    # 401 (not 404) -- valid Redis session but deleted/missing user
    # means stale session. 404 would leak that user_id existed.
    if not user:
        raise UnauthorizedError("Invalid or expired session")

    # Platform user cannot authenticate via API.
    if user.role == UserRole.PLATFORM:
        raise UnauthorizedError("Invalid or expired session")

    if not user.is_active:
        raise ForbiddenError("Account is deactivated")

    # --- Avatar context (Sprint 3.2) ---
    # If this is an avatar session, bind context for logging + audit.
    avatar_session_id = session_data.get("avatar_session_id")
    avatar_staff_id = session_data.get("avatar_staff_id")
    if avatar_session_id and avatar_staff_id:
        structlog.contextvars.bind_contextvars(
            avatar_session_id=avatar_session_id,
            avatar_staff_id=avatar_staff_id,
        )

    return user


async def _load_staff_profile(
    session: AsyncSession,
    user_id: UUID,
) -> StaffProfile | None:
    """Load StaffProfile by user_id. Returns None if not found."""
    stmt = select(StaffProfile).where(StaffProfile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _has_permission(profile: StaffProfile, permission: str) -> bool:
    """Check if a staff member has a specific permission.

    Resolution: profile.permissions[key] ?? DEFAULT_STAFF_PERMISSIONS[key].
    """
    if permission in profile.permissions:
        return bool(profile.permissions[permission])
    return DEFAULT_STAFF_PERMISSIONS.get(permission, False)


async def _get_verified_staff(
    request: Request,
    session: AsyncSession,
) -> tuple[User, StaffProfile]:
    """Load and verify staff user + profile.

    Checks: authenticated, role=staff, StaffProfile exists, is_active.
    Returns (User, StaffProfile) tuple.
    """
    user = await _load_user_from_request(request, session)

    if user.role != UserRole.STAFF:
        raise ForbiddenError("Staff access required")

    profile = await _load_staff_profile(session, user.id)
    if not profile:
        raise ForbiddenError("Staff profile not found")
    if not profile.is_active:
        raise ForbiddenError("Staff profile deactivated")

    return user, profile


# ---------------------------------------------------------------------------
# Public dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> User:
    """Require authenticated user. Returns User or raises 401/403.

    Loads user via read-only session (get_db_reader).
    Use for read-only endpoints.

    Usage: user: User = Depends(get_current_user)
    """
    return await _load_user_from_request(request, session)


async def get_current_user_write(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Require authenticated user, bound to the write session.

    TD-029: use on mutating endpoints that need the user object in
    the same write session as their DB writes. FastAPI caches Depends
    within a request, so Depends(get_db_session) in the router returns
    the SAME session instance -- no merge needed.

    Usage: user: User = Depends(get_current_user_write)
    """
    return await _load_user_from_request(request, session)


async def get_optional_user(
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> User | None:
    """Optional authentication. Returns User or None.

    Does not raise 401 if token is missing. Raises 401 only if
    a token IS provided but is invalid/expired.

    Usage: user: User | None = Depends(get_optional_user)
    """
    if not _extract_token(request):
        return None
    return await _load_user_from_request(request, session)


async def get_current_staff(
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> User:
    """Require authenticated staff user with active StaffProfile.

    Sprint 3.1: verifies role=staff, loads StaffProfile, checks is_active.
    Does NOT check specific permissions -- use require_staff_permission()
    for that.

    Usage: staff: User = Depends(get_current_staff)
    """
    user, _profile = await _get_verified_staff(request, session)
    return user


def require_staff_permission(permission: str) -> Callable:
    """Factory: dependency that requires a specific staff permission.

    Performs full staff verification (role + profile + is_active) plus
    checks that the resolved permission is True.

    Args:
        permission: key from VALID_PERMISSION_KEYS.

    Returns:
        FastAPI dependency function that returns User.

    Raises:
        ValueError: at import time if permission key is unknown (dev guard).

    Usage:
        staff: User = Depends(require_staff_permission("kyc_approve"))
    """
    if permission not in VALID_PERMISSION_KEYS:
        raise ValueError(
            f"Unknown permission: '{permission}'. "
            f"Valid: {sorted(VALID_PERMISSION_KEYS)}"
        )

    async def _dependency(
        request: Request,
        session: AsyncSession = Depends(get_db_reader),
    ) -> User:
        user, profile = await _get_verified_staff(request, session)
        if not _has_permission(profile, permission):
            raise ForbiddenError(f"Missing permission: {permission}")
        return user

    # Set a meaningful name for FastAPI's dependency resolution.
    _dependency.__name__ = f"require_{permission}"
    _dependency.__qualname__ = f"require_staff_permission.<locals>.require_{permission}"

    return _dependency
