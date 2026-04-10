# =============================================================================
# CBSHOME Backend -- Withdrawal Models (Sprint 6.3)
# =============================================================================
#
# Withdrawal:
#   Request to withdraw funds from passive_ledger. Created by any User
#   with confirmed passive balance and configured payout_details.
#
# STATE MACHINE (CBSHOME-State-Machines.md section 4, extended):
#   pending    -> confirmed   (Staff: approved)
#   pending    -> rejected    (Staff: declined with reason)
#   confirmed  -> processing  (system: pushed to payment provider)
#   processing -> completed   (system/webhook: payout confirmed)
#   processing -> failed      (system/webhook: payout rejected)
#
# Terminal statuses: completed, rejected, failed.
#
# LEDGER MECHANICS:
#   - On create: passive_ledger debit (amount_cents negative, confirmed)
#   - On reject/fail: compensating passive_ledger credit (reversal)
#
# CONSTRAINT:
#   Partial unique index on (user_id) WHERE status IN
#   ('pending', 'confirmed', 'processing') -- only one active withdrawal
#   per user at a time.
#
# PAYOUT DETAILS:
#   Snapshot of User.payout_details at creation time. Provider may use
#   this data for automated payouts in future sprints.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import UUIDMixin
from app.modules.withdrawals.constants import WithdrawalStatus


class Withdrawal(UUIDMixin, Base):
    """Withdrawal request from passive_ledger."""

    __tablename__ = "withdrawals"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=WithdrawalStatus.PENDING,
        server_default=WithdrawalStatus.PENDING.value,
        nullable=False,
        index=True,
    )

    # Snapshot of User.payout_details at withdrawal creation time.
    payout_details_snapshot: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=False,
    )

    # Required when status = rejected.
    rejection_reason: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    # -- Timestamps per status transition --

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    processing_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # Only one active withdrawal per user at a time.
        Index(
            "uq_withdrawals_user_active",
            "user_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending', 'confirmed', 'processing')"
            ),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Withdrawal id={self.id} user={self.user_id} "
            f"amount={self.amount_cents} status={self.status}>"
        )
