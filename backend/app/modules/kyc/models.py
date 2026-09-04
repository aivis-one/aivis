# =============================================================================
# AIVIS.ONE Backend -- KYC Models (Sprint 2.1)
# =============================================================================
#
# KYCApplication:
#   Records each KYC submission attempt. Multiple rows per user possible
#   (history: rejected -> resubmit -> approved).
#
# ONE ROW PER PAID SESSION (H10):
#   A row is opened when the fee is charged and carries the decision
#   that closes it. Returning to a session that is still SUBMITTED
#   costs nothing; only a terminal decision makes the next attempt a
#   new, paid row.
#
#   Deliberately minimal: the provider integration pass will add its
#   own fields (applicant reference, external status) by ALTER ADD
#   COLUMN. No column or status member is created here for states
#   nothing currently produces -- a branch for an unreachable state
#   lies to whoever reads it next.
#
# SYNC:
#   On every status change, kyc/service.py updates User.kyc_status
#   (denormalized cache) for fast eligibility checks without JOIN.
# =============================================================================

import enum

from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin


class KYCApplicationStatus(enum.StrEnum):
    """KYC application lifecycle statuses."""

    NOT_STARTED = "not_started"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    # DISTINCT FROM REJECTED, AND THE DISTINCTION IS FOR THE READER OF
    # THE QUEUE. "rejected" says the person did not pass; "revoked" says
    # we took back a decision we had already made. Folding the second
    # into the first would make the audit trail claim the person failed
    # verification when what happened is that staff changed their mind.
    REVOKED = "revoked"


class KYCApplication(UUIDMixin, TimestampMixin, Base):
    """KYC verification application -- one row per submission attempt.

    History is preserved: rejected applications remain in the table,
    new submissions create new rows.
    """

    __tablename__ = "kyc_applications"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=KYCApplicationStatus.SUBMITTED,
        server_default=KYCApplicationStatus.SUBMITTED.value,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<KYCApplication id={self.id} user={self.user_id} "
            f"status={self.status}>"
        )
