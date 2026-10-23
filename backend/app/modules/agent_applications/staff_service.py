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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms import comms_configured
from app.core.config import settings
from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event
from app.core.exceptions import NotFoundError
from app.modules.agent_applications.constants import (
    AgentApplicationStatus,
    validate_transition,
)
from app.modules.agent_applications.models import AgentApplication
from app.modules.users.models import User, UserRole

logger = structlog.get_logger()

# The in-app notice is stored as one text, so it is written in the applicant's
# language: Russian for a Russian account, English for every other one.
_APPROVED_TEXT = {
    "en": (
        "Application approved",
        "Your application has been approved. You are now an agent-integrator. "
        "Accept the agent-integrator agreement to open your cabinet.",
    ),
    "ru": (
        "Заявка одобрена",
        "Ваша заявка одобрена. Вы теперь агент-интегратор. "
        "Примите соглашение агента-интегратора, чтобы открыть кабинет.",
    ),
}


def _approved_text(language: str | None) -> tuple[str, str]:
    return _APPROVED_TEXT["ru" if language == "ru" else "en"]


def _rejected_text(
    language: str | None, reason: str, reapply_after: str
) -> tuple[str, str]:
    if language == "ru":
        return (
            "Заявка отклонена",
            f"Ваша заявка агента-интегратора отклонена: {reason}. "
            f"Подать новую заявку можно после {reapply_after}.",
        )
    return (
        "Application rejected",
        f"Your agent-integrator application was rejected: {reason}. "
        f"You can reapply after {reapply_after}.",
    )


async def agent_application_queue(
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[tuple[AgentApplication, User]], int]:
    """Pending agent applications, oldest first, one page of them.

    Each row is the application together with its applicant's user row
    (name, e-mail and KYC status are read from it). Returns
    (rows, total pending).
    """
    pending = AgentApplication.status == AgentApplicationStatus.PENDING
    total = (
        await session.execute(
            select(func.count()).select_from(AgentApplication).where(pending)
        )
    ).scalar_one()
    stmt = (
        select(AgentApplication, User)
        .join(User, User.id == AgentApplication.user_id)
        .where(pending)
        .order_by(AgentApplication.created_at.asc(), AgentApplication.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    return [(a, u) for a, u in result.all()], total


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

    # Batch 6 (2026-08-28): mirrors kyc.approved/kyc.rejected one level up
    # -- one decision per application row, ever (validate_transition only
    # allows PENDING -> APPROVED, a one-way edge), so the application id
    # alone is a safe, permanent dedup key.
    if comms_configured():
        title, body = _approved_text(user.language)
        await emit_event(
            session,
            EVENT_NOTIFICATION_REQUEST,
            {
                "idempotency_key": f"agent-application-approved:{application.id}",
                "type": "agent_application.approved",
                "target_type": "user",
                "target_value": str(application.user_id),
                "title": title,
                "body": body,
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

    # Batch 6 (2026-08-28): mirrors kyc.approved/kyc.rejected. Body
    # includes the staff reason (already user-facing via GET /me, same
    # precedent withdrawal.rejected's emitter relies on) and the
    # cooldown_until date so the applicant knows when they can reapply.
    if comms_configured():
        applicant = (
            await session.execute(select(User).where(User.id == application.user_id))
        ).scalar_one()
        title, body = _rejected_text(
            applicant.language, reason, application.cooldown_until.date().isoformat()
        )
        await emit_event(
            session,
            EVENT_NOTIFICATION_REQUEST,
            {
                "idempotency_key": f"agent-application-rejected:{application.id}",
                "type": "agent_application.rejected",
                "target_type": "user",
                "target_value": str(application.user_id),
                "title": title,
                "body": body,
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
