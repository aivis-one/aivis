# =============================================================================
# CBSHOME Backend -- Agent Application Model (Sprint 7.1)
# =============================================================================
#
# AgentApplication:
#   Records each agent role application. Multiple rows per user possible
#   (history: rejected -> cooldown -> resubmit).
#
# RULES:
#   - Only one pending application per user (enforced by partial unique index).
#   - On approve: user.role changes to agent (done in staff_service).
#   - On reject: cooldown_until is set; new submission blocked until then.
#   - Approved is terminal -- row preserved for compliance history.
#
# COLUMNS:
#   All use String (not SAEnum) to avoid PostgreSQL type conflicts.
#   CHECK constraint on status enforced via migration ALTER TABLE.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin
from app.modules.agent_applications.constants import AgentApplicationStatus


class AgentApplication(UUIDMixin, TimestampMixin, Base):
    """Agent role application -- one row per submission attempt.

    History is preserved: rejected applications remain in the table,
    new submissions create new rows after cooldown expires.
    """

    __tablename__ = "agent_applications"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=AgentApplicationStatus.PENDING,
        server_default=AgentApplicationStatus.PENDING.value,
        nullable=False,
    )

    # -- Rejection --
    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # -- Cooldown (set on rejection) --
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -- Staff review --
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AgentApplication id={self.id} user={self.user_id} "
            f"status={self.status}>"
        )
