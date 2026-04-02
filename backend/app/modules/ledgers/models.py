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
# CIRCULAR FK (origin_payment_id):
#   payments.id -> payments table (created in Sprint 5.2).
#   Declared as deferrable to avoid circular dependency at migration time.
#   Initially set to NULL for all Sprint 0.3 entries.
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

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy import Enum as SAEnum
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
    Cannot be withdrawn directly -- funds must go through purchases.

    Immutable: no updated_at, entries never deleted.
    """

    __tablename__ = "active_ledger"

    # -- Owner --
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Amount --
    # Positive = credit (deposit), negative = debit (purchase).
    # Integer cents (USD). No floats.
    amount_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # -- Status --
    status: Mapped[str] = mapped_column(
        SAEnum(LedgerStatus, name="ledger_status", create_type=True),
        nullable=False,
        index=True,
    )

    # -- Freeze window --
    # Not null while payment is awaiting confirmation.
    # Daemon transitions frozen -> confirmed when frozen_until <= now().
    frozen_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -- Payment link (circular FK, deferrable) --
    # Links back to payments.id. Circular because Payment also references
    # ledger entries. Deferrable allows both tables to exist independently.
    # NULL until Sprint 5.2 when payments module is created.
    origin_payment_id: Mapped[UUID | None] = mapped_column(
        # ForeignKey added in Sprint 5.2 migration when payments table exists.
        # Declared as plain UUID here to avoid circular dependency.
        nullable=True,
    )

    # -- Reason (canonical LedgerReason string) --
    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # -- Immutable timestamp --
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

    Funded by: distribution saga (company revenue, agent commissions,
               referral bonuses, volume bonuses).
    Withdrawn: to external wallets (crypto/fiat) via Withdrawal requests.
    Only confirmed balance can be withdrawn.

    Immutable: no updated_at, entries never deleted.
    """

    __tablename__ = "passive_ledger"

    # -- Owner --
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # -- Amount --
    amount_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # -- Status --
    status: Mapped[str] = mapped_column(
        SAEnum(LedgerStatus, name="ledger_status", create_type=False),
        # create_type=False: enum already created by ActiveLedger
        nullable=False,
        index=True,
    )

    # -- Freeze window --
    # Used for cooling-off period (14-day EU fiat chargeback protection).
    frozen_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # -- Payment link (see ActiveLedger note) --
    origin_payment_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    # -- Reason --
    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # -- Immutable timestamp --
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
