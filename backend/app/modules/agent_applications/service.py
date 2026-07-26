# =============================================================================
# AIVIS.ONE Backend -- Agent Application Service (Sprint 7.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   submit_application()    -- create AgentApplication (investor only)
#   get_my_applications()   -- list all applications for current user
#
# RULES:
#   - Only investors can submit (role guard).
#   - One pending application per user (partial unique index + service check).
#   - Cooldown enforced: if latest rejected application has
#     cooldown_until > now(), submission is blocked.
#   - Service never commits (P-01).
#   - begin_nested() + IntegrityError catch for concurrent submission race.
# =============================================================================

from datetime import datetime, UTC

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError
from app.modules.agent_applications.constants import AgentApplicationStatus
from app.modules.agent_applications.models import AgentApplication
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


async def submit_application(
    user: User,
    session: AsyncSession,
) -> AgentApplication:
    """Submit a new agent application.

    Raises:
        BadRequestError: If user is not an investor.
        BadRequestError: If cooldown has not expired.
        ConflictError: If user already has a pending application.
    """
    # -- Role guard --
    if user.role != UserRole.INVESTOR:
        raise BadRequestError(
            f"Only investors can apply for agent role. Current role: {user.role}"
        )

    # -- Check for existing pending application --
    stmt = (
        select(AgentApplication)
        .where(
            AgentApplication.user_id == user.id,
            AgentApplication.status == AgentApplicationStatus.PENDING,
        )
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise ConflictError("Agent application already pending")

    # -- Check cooldown from latest rejected application --
    stmt_cooldown = (
        select(AgentApplication)
        .where(
            AgentApplication.user_id == user.id,
            AgentApplication.status == AgentApplicationStatus.REJECTED,
            AgentApplication.cooldown_until.isnot(None),
        )
        .order_by(AgentApplication.created_at.desc())
        .limit(1)
    )
    result_cooldown = await session.execute(stmt_cooldown)
    latest_rejected = result_cooldown.scalar_one_or_none()

    if latest_rejected is not None and latest_rejected.cooldown_until is not None:
        now = datetime.now(UTC)
        if now < latest_rejected.cooldown_until:
            raise BadRequestError(
                f"Cooldown active until {latest_rejected.cooldown_until.isoformat()}. "
                f"Please try again later."
            )

    # -- Create application with SAVEPOINT for race condition --
    application = AgentApplication(
        user_id=user.id,
        status=AgentApplicationStatus.PENDING,
    )
    session.add(application)

    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        if "uq_agent_applications_user_pending" in str(exc.orig):
            raise ConflictError("Agent application already pending")
        raise

    await session.refresh(application)

    await record_audit(
        session=session,
        event="agent_application.submitted",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"application_id": str(application.id)},
    )

    logger.info(
        "agent_application_submitted",
        user_id=str(user.id),
        application_id=str(application.id),
    )

    return application


async def get_my_applications(
    user_id,
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[AgentApplication], int]:
    """List all agent applications for a user (newest first).

    Returns:
        Tuple of (items, total_count).
    """
    # Count.
    count_stmt = (
        select(func.count())
        .select_from(AgentApplication)
        .where(AgentApplication.user_id == user_id)
    )
    total = (await session.execute(count_stmt)).scalar_one()

    # Items.
    stmt = (
        select(AgentApplication)
        .where(AgentApplication.user_id == user_id)
        .order_by(AgentApplication.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    items = list(result.scalars().all())

    return items, total
