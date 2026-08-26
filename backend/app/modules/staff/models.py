# =============================================================================
# AIVIS.ONE Backend -- Staff Models
# =============================================================================
#
# StaffProfile:
#   One-to-one with User (role=staff). Contains permission matrix and
#   operational status. Permissions override config defaults per-staff.
#
# AvatarSession:
#   Records when a Staff member operates as another user for support.
#   Full audit trail: who entered, under whom, when, from which IP.
#   The real user's session is NOT affected -- two independent clients.
#
# AVATAR MECHANICS:
#   1. Staff calls POST /staff/avatar/start {target_user_id}
#   2. System creates AvatarSession, returns child session token
#   3. Child token contains avatar_session_id
#   4. TraceIdMiddleware reads avatar_session_id from Redis session,
#      binds to structlog contextvars -- every log line is annotated
#   5. All mutating operations write performed_by + on_behalf_of to AuditLog
#   6. Staff calls POST /staff/avatar/end -> AvatarSession.status = ended
# =============================================================================

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, UUIDMixin


class AvatarSessionStatus(enum.StrEnum):
    """Status of an avatar session."""

    ACTIVE = "active"
    ENDED = "ended"


class StaffProfile(JSONBMixin, UUIDMixin, Base):
    """Staff profile -- one-to-one with User (role=staff).

    Contains permission matrix overriding config defaults.
    No updated_at: permission changes are tracked via AuditLog.
    """

    __tablename__ = "staff_profiles"

    # -- One-to-one with User --
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # -- Permission matrix (JSONB) --
    # Overrides config defaults per staff member. One bool per key.
    #
    # THE KEYS ARE NOT LISTED HERE, and their absence is the point.
    # staff/constants.py owns them -- DEFAULT_STAFF_PERMISSIONS defines
    # the set and VALID_PERMISSION_KEYS is derived from it -- so a copy
    # in this comment is a second source that can only ever fall behind
    # the first. It did: the list that used to stand here named seven
    # keys while the constant had grown to ten, and a handoff written
    # from this comment inherited the wrong number.
    #
    # Read the set from staff/constants.py. Do not re-enumerate it here.
    #
    # Use set_jsonb("permissions", value) for mutations.
    permissions: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    # -- Operational status --
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    # -- Immutable timestamp (no updated_at) --
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<StaffProfile user_id={self.user_id} active={self.is_active}>"


class AvatarSession(UUIDMixin, Base):
    """Avatar session -- Staff operating as another user.

    Immutable record: created_at only, ended_at set on end.
    The staff_id and target_user_id never change after creation.
    """

    __tablename__ = "avatar_sessions"

    # -- Participants --
    staff_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    target_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Status --
    status: Mapped[str] = mapped_column(
        String(10),
        default=AvatarSessionStatus.ACTIVE,
        server_default=AvatarSessionStatus.ACTIVE.value,
        nullable=False,
    )

    # -- Origin --
    ip_address: Mapped[str] = mapped_column(
        String(45),  # IPv6 max length
        nullable=False,
    )

    # -- Timestamps --
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AvatarSession id={self.id} staff={self.staff_id} "
            f"target={self.target_user_id} status={self.status}>"
        )
