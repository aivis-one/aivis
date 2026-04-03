# =============================================================================
# CBSHOME Backend -- Users Router (Sprint 1.3)
# =============================================================================
#
# ENDPOINTS:
#   GET   /api/v1/users/me  -- Get current user profile
#   PATCH /api/v1/users/me  -- Update current user profile
#
# TD-029 PATTERN:
#   PATCH uses get_current_user_write (write session). Both the dependency
#   and the router declare Depends(get_db_session), so FastAPI reuses
#   the same session instance -- one DB connection, no merge needed.
#
# GET uses get_current_user (read-only session) -- no extra DB query,
# user is already loaded by the dependency.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.users.models import User
from app.modules.users.schemas import UserResponse, UserUpdate
from app.modules.users.service import update_user

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the authenticated user's profile.

    User object is loaded by get_current_user dependency (read-only session).
    No extra DB query needed.
    """
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Update the authenticated user's profile.

    TD-029: get_current_user_write and Depends(get_db_session) share
    the same session instance (FastAPI caches Depends within a request).
    The user is already bound to the write session -- no merge needed.

    Only fields present in the request body are updated (exclude_unset).
    """
    updated = await update_user(user, body, session)
    return UserResponse.model_validate(updated)
