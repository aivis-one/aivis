# =============================================================================
# AIVIS.ONE Backend -- Avatar Service (Sprint 3.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   start_avatar()      -- create AvatarSession + Redis avatar token
#   end_avatar()        -- close active avatar session + delete Redis token
#   get_active_avatar() -- find active AvatarSession for staff
#
# AVATAR TOKEN MECHANICS:
#   Avatar tokens are separate from regular user sessions:
#   - NOT added to user_sessions:{user_id} ZSET (no slot occupied)
#   - NOT evicted by user's logout-all
#   - session:{token} contains avatar_session_id + avatar_staff_id
#   - avatar_token:{avatar_session_id} -> token (reverse lookup for /end)
#   - Own TTL (avatar_session_ttl_hours, default 8h), independent of
#     session_ttl_days -- TASK-6 4.3. Orphans cleaned by Redis TTL, but
#     the real revocation authority is AvatarSession.status in the DB,
#     re-checked on every request (auth/dependencies.py); Redis expiry
#     is only the outer bound.
#
# SESSION DATA FORMAT:
#   {
#     "user_id": "<target_user_id>",
#     "auth_method": "avatar",
#     "created_at": "iso",
#     "avatar_session_id": "<avatar_session.id>",
#     "avatar_staff_id": "<staff.id>"
#   }
#
# RULES:
#   - Staff can have only one active avatar (previous auto-closed)
#   - Staff cannot avatar into another staff user
#   - Staff cannot avatar into platform user
#   - Permission avatar_mode required
#   - /end uses staff's original token, not avatar token
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

import json
import secrets
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.redis import get_redis
from app.modules.staff.models import AvatarSession, AvatarSessionStatus
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

# Redis key prefixes for avatar tokens.
_SESSION_PREFIX = "session:"
_AVATAR_TOKEN_PREFIX = "avatar_token:"


def _get_avatar_ttl() -> int:
    """Return avatar session TTL in seconds from config.

    Independent of session_ttl_days (TASK-6 4.3) -- an impersonation
    session must not outlive the shift it was opened for.
    """
    return settings.avatar_session_ttl_hours * 3600


async def _close_avatar_session(
    avatar_session: AvatarSession,
    session: AsyncSession,
) -> None:
    """Close an avatar session: update DB + delete Redis keys."""
    avatar_session.status = AvatarSessionStatus.ENDED
    avatar_session.ended_at = datetime.now(UTC)
    await session.flush()

    # Delete Redis avatar token via reverse lookup.
    redis = get_redis()
    avatar_key = f"{_AVATAR_TOKEN_PREFIX}{avatar_session.id}"
    token = await redis.get(avatar_key)
    if token:
        await redis.delete(f"{_SESSION_PREFIX}{token}", avatar_key)
    else:
        # Reverse key expired (TTL) -- session key may also be gone.
        await redis.delete(avatar_key)

    logger.info(
        "avatar_session_closed",
        avatar_session_id=str(avatar_session.id),
        staff_id=str(avatar_session.staff_id),
        target_user_id=str(avatar_session.target_user_id),
    )


async def _find_active_avatar(
    staff_id: UUID,
    session: AsyncSession,
) -> AvatarSession | None:
    """Find active avatar session for staff. Returns None if none."""
    stmt = (
        select(AvatarSession)
        .where(
            AvatarSession.staff_id == staff_id,
            AvatarSession.status == AvatarSessionStatus.ACTIVE,
        )
        .order_by(AvatarSession.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def start_avatar(
    staff: User,
    target_user_id: UUID,
    ip_address: str,
    session: AsyncSession,
) -> tuple[AvatarSession, str]:
    """Start avatar session: staff operates as target user.

    Auto-closes any previous active avatar for this staff.
    Creates AvatarSession in DB + avatar token in Redis.

    Returns (AvatarSession, session_token).

    Raises:
        NotFoundError: If target user not found.
        BadRequestError: If target is staff or platform user.
    """
    # Load target user.
    stmt = select(User).where(User.id == target_user_id)
    result = await session.execute(stmt)
    target = result.scalar_one_or_none()

    if target is None:
        raise NotFoundError("User not found")

    if target.role == UserRole.STAFF:
        raise BadRequestError("Cannot avatar into staff user")

    if target.role == UserRole.PLATFORM:
        raise BadRequestError("Cannot avatar into platform user")

    # Auto-close previous active avatar for this staff.
    existing = await _find_active_avatar(staff.id, session)
    if existing:
        await _close_avatar_session(existing, session)

        await record_audit(
            session=session,
            event="staff.avatar_ended",
            actor_id=staff.id,
            actor_type="staff",
            target_type="user",
            target_id=existing.target_user_id,
            data={"avatar_session_id": str(existing.id), "reason": "auto_close"},
        )

    # Create AvatarSession in DB.
    avatar = AvatarSession(
        staff_id=staff.id,
        target_user_id=target_user_id,
        status=AvatarSessionStatus.ACTIVE,
        ip_address=ip_address,
    )
    session.add(avatar)
    await session.flush()
    await session.refresh(avatar)

    # Create avatar token in Redis (separate from user ZSET).
    token = secrets.token_urlsafe(48)
    ttl = _get_avatar_ttl()
    redis = get_redis()

    session_data = json.dumps({
        "user_id": str(target_user_id),
        "auth_method": "avatar",
        "created_at": datetime.now(UTC).isoformat(),
        "avatar_session_id": str(avatar.id),
        "avatar_staff_id": str(staff.id),
    })

    # Pipeline: session key + reverse lookup key.
    pipe = redis.pipeline(transaction=True)
    pipe.set(f"{_SESSION_PREFIX}{token}", session_data, ex=ttl)
    pipe.set(f"{_AVATAR_TOKEN_PREFIX}{avatar.id}", token, ex=ttl)
    await pipe.execute()

    # Audit.
    await record_audit(
        session=session,
        event="staff.avatar_started",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=target_user_id,
        data={"avatar_session_id": str(avatar.id)},
    )

    logger.info(
        "avatar_session_started",
        avatar_session_id=str(avatar.id),
        staff_id=str(staff.id),
        target_user_id=str(target_user_id),
    )

    return avatar, token


async def end_avatar(
    staff: User,
    session: AsyncSession,
) -> None:
    """End active avatar session for staff.

    Called with staff's original token.
    Closes AvatarSession in DB + deletes Redis avatar token.

    Raises:
        NotFoundError: If no active avatar session.
    """
    avatar = await _find_active_avatar(staff.id, session)
    if avatar is None:
        raise NotFoundError("No active avatar session")

    await _close_avatar_session(avatar, session)

    # Audit.
    await record_audit(
        session=session,
        event="staff.avatar_ended",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=avatar.target_user_id,
        data={"avatar_session_id": str(avatar.id)},
    )


async def get_active_avatar(
    staff_id: UUID,
    session: AsyncSession,
) -> AvatarSession | None:
    """Get active avatar session for staff. Returns None if none."""
    return await _find_active_avatar(staff_id, session)
