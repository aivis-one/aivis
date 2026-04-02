# =============================================================================
# CBSHOME Backend -- Audit Log
# =============================================================================
#
# AuditLog is the immutable record of all significant system events.
# Used for compliance, financial auditing, and support investigation.
#
# IMMUTABLE:
#   Entries are never updated or deleted. No updated_at.
#   Inherits Base directly (not UUIDMixin/TimestampMixin) to keep
#   the model minimal and prevent accidental mixin timestamp conflicts.
#
# AVATAR CONTEXT:
#   performed_by -- staff_id when operating in avatar mode
#   on_behalf_of -- target_user_id when operating in avatar mode
#   Both NULL for normal user operations.
#
# TRACE ID:
#   Links AuditLog entries to structlog application logs.
#   String(36) = UUID format max length.
#
# RULE (P-01): record_audit() does NOT commit.
#   Caller manages the transaction. AuditLog entry is flushed alongside
#   the business operation in the same atomic transaction.
#
# USAGE:
#   from app.core.audit import record_audit
#   await record_audit(
#       session=session,
#       event="user.registered",
#       actor_id=user.id,
#       actor_type="user",
#       target_type="user",
#       target_id=user.id,
#       data={"role": "investor"},
#   )
# =============================================================================

from datetime import datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

logger = structlog.get_logger()


class AuditLog(Base):
    """Immutable audit trail entry.

    Inherits Base directly -- no UUIDMixin/TimestampMixin to keep
    the model clean and avoid accidental updated_at.
    """

    __tablename__ = "audit_log"

    # -- Primary key (app-side uuid4 for consistency) --
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    # -- Timestamp (immutable, server-side) --
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # -- Event (indexed for filtering) --
    event: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # -- Actor (who performed the action) --
    actor_id: Mapped[UUID | None] = mapped_column(nullable=True)
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        # "user" | "staff" | "system"
    )

    # -- Avatar context (NULL for normal operations) --
    performed_by: Mapped[UUID | None] = mapped_column(
        nullable=True,
        # staff_id when operating in avatar mode
    )
    on_behalf_of: Mapped[UUID | None] = mapped_column(
        nullable=True,
        # target_user_id when operating in avatar mode
    )

    # -- Target (what was acted upon) --
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)

    # -- Event data (arbitrary context) --
    data: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    # -- Request context --
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(
        String(36),  # UUID max length
        nullable=True,
    )

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

    Args:
        session: Active DB session. Caller manages commit.
        event: Event name, e.g. "user.registered", "payment.deposit_created".
        actor_id: UUID of the actor (user/staff/None for system).
        actor_type: "user" | "staff" | "system".
        target_type: Entity type, e.g. "user", "payment", "purchase".
        target_id: UUID of the affected entity.
        data: Additional event context (serializable dict).
        performed_by: Staff UUID when in avatar mode.
        on_behalf_of: Target user UUID when in avatar mode.

    Returns:
        The created AuditLog entry (flushed, not committed).
    """
    import structlog.contextvars as ctx

    # Read request context from structlog contextvars (set by TraceIdMiddleware).
    bound = ctx.get_contextvars()
    trace_id = bound.get("trace_id")
    ip_address = bound.get("ip_address")
    user_agent = bound.get("user_agent")

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
        event=event,
        actor_id=str(actor_id) if actor_id else None,
        target_type=target_type,
        target_id=str(target_id),
    )

    return entry
