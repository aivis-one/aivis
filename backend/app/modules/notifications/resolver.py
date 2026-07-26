# =============================================================================
# AIVIS.ONE Backend -- Notification Resolver (Sprint 8.1)
# =============================================================================
#
# RESPONSIBILITY:
#   Expand target_type + target_value into a list of concrete user UUIDs.
#
# TARGET FORMATS:
#   user:<uuid>   -> single user
#   role:<role>    -> all active users with that role
#   *             -> all active users (excluding platform)
#
# EXTENSIBILITY:
#   New target types can be added by registering a resolver function
#   in _RESOLVERS dict. Each resolver receives (session, target_value)
#   and returns list[UUID].
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.constants import TargetType
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


async def resolve_targets(
    session: AsyncSession,
    target_type: str,
    target_value: str,
) -> list[UUID]:
    """Resolve notification target into concrete user UUIDs.

    Args:
        session: Active DB session.
        target_type: One of TargetType values.
        target_value: Target specifier (format depends on target_type).

    Returns:
        List of user UUIDs to receive the notification.
    """
    resolver = _RESOLVERS.get(target_type)
    if resolver is None:
        logger.warning(
            "unknown_target_type",
            target_type=target_type,
            target_value=target_value,
        )
        return []

    user_ids = await resolver(session, target_value)

    logger.info(
        "targets_resolved",
        target_type=target_type,
        target_value=target_value,
        count=len(user_ids),
    )
    return user_ids


# ---------------------------------------------------------------------------
# Individual resolvers
# ---------------------------------------------------------------------------


async def _resolve_user(
    session: AsyncSession,
    target_value: str,
) -> list[UUID]:
    """Resolve 'user:<uuid>' -> single user if active."""
    # Expected format: "user:<uuid>"
    prefix = "user:"
    if not target_value.startswith(prefix):
        logger.warning("invalid_user_target", target_value=target_value)
        return []

    raw_id = target_value[len(prefix):]
    try:
        user_id = UUID(raw_id)
    except ValueError:
        logger.warning("invalid_user_uuid", target_value=target_value)
        return []

    stmt = select(User.id).where(
        User.id == user_id,
        User.is_active.is_(True),
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return [row] if row else []


async def _resolve_role(
    session: AsyncSession,
    target_value: str,
) -> list[UUID]:
    """Resolve 'role:<role>' -> all active users with that role."""
    # Expected format: "role:<role_name>"
    prefix = "role:"
    if not target_value.startswith(prefix):
        logger.warning("invalid_role_target", target_value=target_value)
        return []

    role_name = target_value[len(prefix):]

    stmt = select(User.id).where(
        User.role == role_name,
        User.is_active.is_(True),
        User.role != UserRole.PLATFORM,
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def _resolve_all(
    session: AsyncSession,
    target_value: str,
) -> list[UUID]:
    """Resolve '*' -> all active non-platform users."""
    stmt = select(User.id).where(
        User.is_active.is_(True),
        User.role != UserRole.PLATFORM,
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


# ---------------------------------------------------------------------------
# Resolver registry -- add new target types here
# ---------------------------------------------------------------------------

_RESOLVERS = {
    TargetType.USER: _resolve_user,
    TargetType.ROLE: _resolve_role,
    TargetType.ALL: _resolve_all,
}
