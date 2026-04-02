# =============================================================================
# CBSHOME Backend -- Auth Dependencies
# =============================================================================
#
# FastAPI dependencies for request authentication.
#
# DEPENDENCY OVERVIEW:
#   get_current_user       -- any authenticated user, read session (get_db_reader)
#   get_current_user_write -- any authenticated user, write session (get_db_session)
#   get_optional_user      -- optional auth, read session; returns None if no token
#   get_current_staff      -- staff role required (Sprint 1.1: role check only;
#                             Sprint 3.1: expanded with permission matrix)
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
# =============================================================================

from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.modules.auth.service import get_session
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

    return user


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
    """Require authenticated staff user.

    Sprint 1.1: checks role == staff only.
    Sprint 3.1: will be expanded to load StaffProfile and check
    specific permissions from the permission matrix.

    Usage: staff: User = Depends(get_current_staff)
    """
    user = await _load_user_from_request(request, session)

    if user.role != UserRole.STAFF:
        raise ForbiddenError("Staff access required")

    return user
