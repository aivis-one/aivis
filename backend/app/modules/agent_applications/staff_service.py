# =============================================================================
# AIVIS.ONE Backend -- Agent Application Staff Service (Sprint 7.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   agent_application_queue()   -- list pending applications
#   agent_application_approve() -- approve application, change user role
#   agent_application_reject()  -- reject application, set cooldown
#
# RULES:
#   - On approve: user.role -> agent (immediate).
#   - On reject: cooldown_until = now() + AGENT_APPLICATION_COOLDOWN_DAYS.
#   - rejection_reason is required for reject.
#   - State machine transitions validated via constants.validate_transition().
#   - SELECT FOR UPDATE on application to serialize concurrent staff actions.
#   - Service never commits (P-01).
# =============================================================================

from datetime import datetime, timedelta, UTC
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.modules.agent_applications.constants import (
    AgentApplicationStatus,
    validate_transition,
)
from app.modules.agent_applications.models import AgentApplication
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()


async def agent_application_queue(
    session: AsyncSession,
) -> list[AgentApplication]:
    """List all pending agent applications (oldest first)."""
    stmt = (
        select(AgentApplication)
        .where(AgentApplication.status == AgentApplicationStatus.PENDING)
        .order_by(AgentApplication.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def agent_application_approve(
    application_id: UUID,
    staff: User,
    session: AsyncSession,
) -> None:
    """Approve an agent application.

    Changes user.role to agent immediately.

    Raises:
        NotFoundError: If application not found.
        BadRequestError: If transition is invalid.
    """
    application = await _load_application(application_id, session)

    # Validate state transition.
    validate_transition(application.status, AgentApplicationStatus.APPROVED)

    now = datetime.now(UTC)

    # Update application.
    application.status = AgentApplicationStatus.APPROVED
    application.reviewed_at = now
    application.reviewed_by = staff.id

    # Change user role to agent.
    stmt = select(User).where(User.id == application.user_id)
    result = await session.execute(stmt)
    user = result.scalar_one()

    old_role = user.role
    user.role = UserRole.AGENT

    await session.flush()

    await record_audit(
        session=session,
        event="agent_application.approved",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=application.user_id,
        data={
            "application_id": str(application.id),
            "old_role": old_role,
            "new_role": UserRole.AGENT,
        },
    )

    logger.info(
        "agent_application_approved",
        application_id=str(application_id),
        user_id=str(application.user_id),
        staff_id=str(staff.id),
    )


async def agent_application_reject(
    application_id: UUID,
    staff: User,
    reason: str,
    session: AsyncSession,
) -> None:
    """Reject an agent application.

    Sets cooldown_until and rejection_reason.

    Raises:
        NotFoundError: If application not found.
        BadRequestError: If transition is invalid.
    """
    application = await _load_application(application_id, session)

    # Validate state transition.
    validate_transition(application.status, AgentApplicationStatus.REJECTED)

    now = datetime.now(UTC)

    # Update application.
    application.status = AgentApplicationStatus.REJECTED
    application.rejection_reason = reason
    application.cooldown_until = now + timedelta(
        days=settings.agent_application_cooldown_days
    )
    application.reviewed_at = now
    application.reviewed_by = staff.id

    await session.flush()

    await record_audit(
        session=session,
        event="agent_application.rejected",
        actor_id=staff.id,
        actor_type="staff",
        target_type="user",
        target_id=application.user_id,
        data={
            "application_id": str(application.id),
            "reason": reason,
            "cooldown_days": settings.agent_application_cooldown_days,
        },
    )

    logger.info(
        "agent_application_rejected",
        application_id=str(application_id),
        user_id=str(application.user_id),
        staff_id=str(staff.id),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_application(
    application_id: UUID,
    session: AsyncSession,
) -> AgentApplication:
    """Load application by ID with FOR UPDATE or raise NotFoundError."""
    stmt = (
        select(AgentApplication)
        .where(AgentApplication.id == application_id)
        .with_for_update()
    )
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    if application is None:
        raise NotFoundError("Agent application not found")

    return application
