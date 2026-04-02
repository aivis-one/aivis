# =============================================================================
# CBSHOME Backend -- Auth Router
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/auth/email/register  -- Register via email + password
#   POST /api/v1/auth/email/login     -- Login via email + password
#   POST /api/v1/auth/logout          -- Logout current session
#   POST /api/v1/auth/logout-all      -- Logout all sessions
#
# Sprint 1.2 adds: POST /api/v1/auth/telegram
#
# SESSION MANAGEMENT:
#   Register and login create a Redis session and return AuthResponse.
#   Logout deletes the current session. Logout-all deletes every session
#   for the user (Lua script, atomic).
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield. Routers call flush() to get IDs.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import (
    AuthResponse,
    EmailLoginRequest,
    EmailRegisterRequest,
)
from app.modules.auth.service import (
    create_session,
    delete_all_sessions,
    delete_session,
    login_email,
    register_email,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/email/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def auth_email_register(
    body: EmailRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Register a new user via email + password.

    Flow:
      1. Create User (role=investor, credentials with hashed password)
      2. Flush to get user.id (commit deferred to get_db_session)
      3. Create Redis session
      4. Return AuthResponse
    """
    user = await register_email(body.email, body.password, session)
    await session.flush()

    token = await create_session(user, auth_method="email")

    return AuthResponse(
        user=user,  # type: ignore[arg-type]
        session_token=token,
    )


@router.post(
    "/email/login",
    response_model=AuthResponse,
)
async def auth_email_login(
    body: EmailLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Login via email + password.

    Flow:
      1. Lookup user by email (JSONB functional index)
      2. Verify argon2 hash
      3. Guard: platform user, deactivated account
      4. Create Redis session (enforces MAX_CONCURRENT_SESSIONS)
      5. Return AuthResponse
    """
    user = await login_email(body.email, body.password, session)
    await session.flush()

    token = await create_session(user, auth_method="email")

    return AuthResponse(
        user=user,  # type: ignore[arg-type]
        session_token=token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def auth_logout(
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Logout current session -- delete from Redis."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    if token:
        await delete_session(token, user_id=user.id)

    logger.info("user_logout", user_id=str(user.id))


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def auth_logout_all(
    user: User = Depends(get_current_user),
) -> None:
    """Logout all sessions for the current user.

    Invalidates every active session token via atomic Lua script.
    The current request succeeds (user already authenticated), but
    all subsequent requests with any token will fail with 401.
    """
    count = await delete_all_sessions(user.id)

    logger.info(
        "user_logout_all",
        user_id=str(user.id),
        sessions_invalidated=count,
    )
