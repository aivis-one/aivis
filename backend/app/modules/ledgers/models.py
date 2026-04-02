# =============================================================================
# CBSHOME Backend -- Ledger Models
# =============================================================================
#
# Double-entry ledger system. Every User has exactly two ledgers:
#
#   active_ledger  -- external money in (deposits, purchases out)
#   passive_ledger -- system money in (commissions, revenue, bonuses out)
#
# IMMUTABLE:
#   Ledger entries are never deleted or updated. Status changes via UPDATE
#   on the status column only. Reversals create mirror entries with
#   reason + ":reversal" suffix.
#
# NO updated_at:
#   created_at is the only timestamp. Entries are immutable records.
#
# AMOUNT:
#   BigInteger (64-bit) to support platform-level balances.
#   Integer (32-bit) max is ~$21.4M -- insufficient for an investment platform.
#   BigInteger max is ~$92 trillion -- no practical limit.
#
# AML MATRIX:
#   Active -> Passive route is forbidden.
#   Enforced by ledgers/service.py on every write, not at DB level.
#   See CBSHOME-Financial-System.md section 3.
#
# AMOUNT CONVENTION:
#   Positive = credit (money coming in to this ledger)
#   Negative = debit  (money going out from this ledger)
#   SUM(all entries across all ledgers) = 0 always (semaphore S-01)
# =============================================================================

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import UUIDMixin


class LedgerStatus(enum.StrEnum):
    """Status of a ledger entry."""

    FROZEN = "frozen"        # received but not yet confirmed
    CONFIRMED = "confirmed"  # fully available
    REVERSED = "reversed"    # chargeback applied, mirror entry created


class ActiveLedger(UUIDMixin, Base):
    """Active ledger -- external money flowing in and out.

    Funded by: crypto deposits, bank transfers (fiat, Phase 2).
    Spent on:  product purchases only.

    Immutable: no updated_at, entries never deleted.
    """

    __tablename__ = "active_ledger"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # BigInteger: supports up to ~$92 trillion. Integer max is ~$21.4M.
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    frozen_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Circular FK to payments.id -- added in Sprint 5.2 migration.
    origin_payment_id: Mapped[UUID | None] = mapped_column(nullable=True)

    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_active_ledger_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<ActiveLedger id={self.id} user={self.user_id} "
            f"amount={self.amount_cents} status={self.status}>"
        )


class PassiveLedger(UUIDMixin, Base):
    """Passive ledger -- system money (commissions, revenue, bonuses).

    Funded by: distribution saga.
    Withdrawn: to external wallets via Withdrawal requests.

    Immutable: no updated_at, entries never deleted.
    """

    __tablename__ = "passive_ledger"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # BigInteger: see ActiveLedger note.
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    frozen_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    origin_payment_id: Mapped[UUID | None] = mapped_column(nullable=True)

    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_passive_ledger_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<PassiveLedger id={self.id} user={self.user_id} "
            f"amount={self.amount_cents} status={self.status}>"
        )
