# =============================================================================
# CBSHOME Backend -- KYC Models (Sprint 2.1)
# =============================================================================
#
# KYCApplication:
#   Records each KYC submission attempt. Multiple rows per user possible
#   (history: rejected -> resubmit -> approved).
#
# STUB:
#   This is a stub module. Real SumSub integration (TD-003) will add
#   fields like applicant_id, external_status, rejection_reason via
#   ALTER ADD COLUMN. Current model is intentionally minimal.
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
