# =============================================================================
# AIVIS.ONE Backend -- Transaction Models (Sprint 6.4)
# =============================================================================
#
# Transaction:
#   Immutable event log. Each row records a single fact about a financial
#   operation. No UPDATE ever -- new events create new rows.
#
#   Grouped by (reference_id, reference_type) to show lifecycle of one
#   entity (e.g. all events for a single withdrawal).
#
# AMOUNT:
#   Always the operation amount for display purposes, even for status
#   transition events (e.g. withdrawal:confirmed repeats the amount).
#   Positive = money in (deposit, refund). Negative = money out (purchase,
#   withdrawal). Convention matches active_ledger sign.
#
# DETAILS JSONB:
#   Type-specific metadata for frontend display. Examples:
#     deposit:received  -> {network, tx_hash, from_address}
#     purchase:completed -> {product_name, units, price_per_unit_cents}
#     withdrawal:rejected -> {reason}
#
# NO updated_at:
#   Immutable records. created_at is the only timestamp.
#
# RULES:
#   - All columns use String (not SAEnum) -- project convention
#   - amount_cents is BigInteger (consistent with ledger)
#   - details mutations via set_jsonb() only (JSONBMixin)
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, UUIDMixin


class Transaction(UUIDMixin, JSONBMixin, Base):
    """Immutable financial event log entry."""

    __tablename__ = "transactions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Event type: "deposit:received", "purchase:completed", etc.
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # Operation amount in cents. Always filled for display.
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        server_default="USD",
        nullable=False,
    )

    # Link to the source entity for lifecycle grouping.
    reference_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    # Type of the referenced entity: payment, purchase, withdrawal, etc.
    reference_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    # Type-specific metadata for frontend display.
    details: Mapped[dict | None] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # Primary query: user's transaction history sorted by date.
        Index("ix_transactions_user_created", "user_id", "created_at"),
        # Lifecycle grouping: all events for one entity.
        Index("ix_transactions_reference", "reference_id", "reference_type"),
        # Filter by type prefix.
        Index("ix_transactions_type", "type"),
    )

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} user={self.user_id} "
            f"type={self.type} amount={self.amount_cents}>"
        )
