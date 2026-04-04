# =============================================================================
# CBSHOME Backend -- Audit Log
# =============================================================================
#
# AuditLog is the immutable record of all significant system events.
# Used for compliance, financial auditing, and support investigation.
#
# IMMUTABLE:
#   Entries are never updated or deleted. No updated_at.
#   Inherits Base directly (not UUIDMixin/TimestampMixin).
#
# AVATAR CONTEXT (Sprint 3.2):
#   performed_by -- staff_id when operating in avatar mode
#   on_behalf_of -- target_user_id when operating in avatar mode
#   Both NULL for normal user operations.
#
#   AUTO-FILL: If avatar_staff_id is present in structlog contextvars
#   and caller did not explicitly pass performed_by, record_audit()
#   automatically fills performed_by=staff_id and on_behalf_of=actor_id.
#   Existing code does not need changes to support avatar auditing.
#
# TRACE ID:
#   Links AuditLog entries to structlog application logs.
#   String(36) = UUID format max length.
#
# RULE (P-01): record_audit() does NOT commit.
#   Caller manages the transaction. AuditLog entry is flushed alongside
#   the business operation in the same atomic transaction.
#
# USER AGENT:
#   Truncated to USER_AGENT_MAX_LEN chars to prevent DoS via oversized
#   headers. Constant shared with middleware.py via core/constants.py.
# =============================================================================

from datetime import datetime
from uuid import UUID, uuid4

import structlog
import structlog.contextvars
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import USER_AGENT_MAX_LEN
from app.core.database import Base

logger = structlog.get_logger()


class AuditLog(Base):
    """Immutable audit trail entry."""

    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    event: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    actor_id: Mapped[UUID | None] = mapped_column(nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        # "user" | "staff" | "system"
    )

    # Avatar context (NULL for normal operations).
    performed_by: Mapped[UUID | None] = mapped_column(nullable=True)
    on_behalf_of: Mapped[UUID | None] = mapped_column(nullable=True)

    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)

    data: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    # user_agent: truncated to USER_AGENT_MAX_LEN to prevent disk exhaustion.
    user_agent: Mapped[str | None] = mapped_column(
        String(USER_AGENT_MAX_LEN), nullable=True
    )
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_audit_log_event_created", "event", "created_at"),
        Index("ix_audit_log_target", "target_type", "target_id"),
        Index("ix_audit_log_actor", "actor_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} event={self.event} "
            f"actor={self.actor_id} target={self.target_id}>"
        )


async def record_audit(
    session: AsyncSession,
    *,
    event: str,
    actor_id: UUID | None,
    actor_type: str,
    target_type: str,
    target_id: UUID,
    data: dict | None = None,  # type: ignore[type-arg]
    performed_by: UUID | None = None,
    on_behalf_of: UUID | None = None,
) -> AuditLog:
    """Create an AuditLog entry. Does NOT commit (P-01).

    Reads trace_id, ip_address, user_agent from structlog contextvars
    set by TraceIdMiddleware. No need to pass them explicitly.

    Sprint 3.2 auto-fill: If avatar_staff_id is in contextvars and
    performed_by is not explicitly passed, auto-fills:
      performed_by = avatar_staff_id (the staff doing the action)
      on_behalf_of = actor_id (the user being acted upon)

    Args:
        session: Active DB session. Caller manages commit.
        event: Event name, e.g. "user.registered".
        actor_id: UUID of the actor (user/staff/None for system).
        actor_type: "user" | "staff" | "system".
        target_type: Entity type, e.g. "user", "payment".
        target_id: UUID of the affected entity.
        data: Additional event context (serializable dict).
        performed_by: Staff UUID when in avatar mode (auto-filled if None).
        on_behalf_of: Target user UUID when in avatar mode (auto-filled if None).

    Returns:
        The created AuditLog entry (flushed, not committed).
    """
    # Read request context from structlog contextvars (set by TraceIdMiddleware).
    bound = structlog.contextvars.get_contextvars()
    trace_id = bound.get("trace_id")
    ip_address = bound.get("ip_address")
    raw_user_agent = bound.get("user_agent")

    # Avatar auto-fill: if in avatar mode and caller didn't explicitly set.
    if performed_by is None:
        avatar_staff_id = bound.get("avatar_staff_id")
        if avatar_staff_id:
            performed_by = UUID(avatar_staff_id)
            on_behalf_of = actor_id

    # Truncate user_agent to prevent disk exhaustion via oversized headers.
    user_agent: str | None = None
    if raw_user_agent:
        user_agent = str(raw_user_agent)[:USER_AGENT_MAX_LEN]

    entry = AuditLog(
        event=event,
        actor_id=actor_id,
        actor_type=actor_type,
        performed_by=performed_by,
        on_behalf_of=on_behalf_of,
        target_type=target_type,
        target_id=target_id,
        data=data or {},
        ip_address=ip_address,
        user_agent=user_agent,
        trace_id=str(trace_id)[:36] if trace_id else None,
    )
    session.add(entry)
    await session.flush()

    logger.info(
        "audit_recorded",
        audit_event=event,
        actor_id=str(actor_id) if actor_id else None,
        target_type=target_type,
        target_id=str(target_id),
    )

    return entry
