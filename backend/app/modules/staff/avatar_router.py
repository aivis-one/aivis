# =============================================================================
# AIVIS.ONE Backend -- Avatar Router (Sprint 3.2)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/staff/avatar/start   -- start avatar session (avatar_mode perm)
#   POST /api/v1/staff/avatar/end     -- end active avatar (any staff)
#   GET  /api/v1/staff/avatar/active  -- get active avatar session (any staff)
#
# AUTH:
#   /start requires avatar_mode permission via require_staff_permission.
#   /end and /active require get_current_staff (any staff).
#   All use staff's original token -- NOT the avatar token.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_staff, require_staff_permission
from app.modules.staff.avatar_schemas import (
    AvatarSessionResponse,
    AvatarStartRequest,
    AvatarStartResponse,
)
from app.modules.staff.avatar_service import (
    end_avatar,
    get_active_avatar,
    start_avatar,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/avatar", tags=["staff-avatar"])


@router.post(
    "/start",
    response_model=AvatarStartResponse,
    status_code=status.HTTP_200_OK,
)
async def avatar_start(
    body: AvatarStartRequest,
    request: Request,
    staff: User = Depends(require_staff_permission("avatar_mode")),
    session: AsyncSession = Depends(get_db_session),
) -> AvatarStartResponse:
    """Start avatar session -- staff operates as target user.

    Auto-closes any previous active avatar for this staff.
    Returns avatar session ID and a dedicated session token.
    """
    # Read IP from structlog contextvars (set by TraceIdMiddleware).
    import structlog.contextvars
    ctx = structlog.contextvars.get_contextvars()
    ip_address = ctx.get("ip_address", "unknown")

    avatar, token = await start_avatar(staff, body.target_user_id, ip_address, session)

    return AvatarStartResponse(
        avatar_session_id=avatar.id,
        session_token=token,
    )


@router.post(
    "/end",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def avatar_end(
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """End active avatar session. Uses staff's original token."""
    await end_avatar(staff, session)


@router.get(
    "/active",
    response_model=AvatarSessionResponse | None,
)
async def avatar_active(
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_reader),
) -> AvatarSessionResponse | None:
    """Get active avatar session for current staff. Returns null if none."""
    avatar = await get_active_avatar(staff.id, session)
    if avatar is None:
        return None
    return AvatarSessionResponse.model_validate(avatar)
