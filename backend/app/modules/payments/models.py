# =============================================================================
# CBSHOME Backend -- Payment Models (Sprint 5.2)
# =============================================================================
#
# Payment:
#   Incoming payments from investors only. Each payment creates a
#   corresponding active_ledger entry via the webhook flow.
#
#   Status lifecycle: created -> frozen -> confirmed (or reversed/failed).
#   See CBSHOME-State-Machines.md section 1.
#
#   provider_data is JSONB -- schema depends on payment_type:
#     crypto: {network, to_address, from_address, tx_hash, ...}
#     bank:   {bank_name, iban, swift, bank_reference, ...}
#
# CryptoAddress:
#   Internal table -- not exposed outside payments/ module.
#   One address per (user_id, network) pair.
#   Stub: address is generated as a placeholder UUID string.
#   Real integration will come from blockchain provider API.
#
# RULES:
#   - All columns use String (not SAEnum) -- project convention
#   - amount_cents is BigInteger (same as ledger)
#   - provider_data mutations via set_jsonb() only (JSONBMixin)
#   - Payment has updated_at (status changes), unlike immutable ledger
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, UUIDMixin


class Payment(UUIDMixin, JSONBMixin, Base):
    """Incoming payment from an investor.

    Lifecycle: created -> frozen -> confirmed (or reversed/failed).
    """

    __tablename__ = "payments"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # BigInteger: consistent with ledger tables.
    amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        server_default="USD",
        nullable=False,
    )

    # "crypto" | "bank" -- from PaymentType enum.
    payment_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Provider identifier: "crypto_usdt_trc20", "bank_swift", etc.
    provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Lifecycle status -- from PaymentStatus enum.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    # Payment expires if not completed by this time.
    # created -> failed when expires_at <= now().
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Cooling-off period end. Set when created -> frozen.
    # frozen -> confirmed when frozen_until <= now().
    frozen_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Provider-specific data. Schema depends on payment_type.
    # Mutated via set_jsonb() only (JSONBMixin).
    provider_data: Mapped[dict | None] = mapped_column(  # type: ignore[type-arg]
        JSONB,
        nullable=True,
    )

    # For reversal chain -- links to the original payment being reversed.
    origin_payment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_payments_user_status", "user_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} user={self.user_id} "
            f"amount={self.amount_cents} status={self.status}>"
        )


class CryptoAddress(UUIDMixin, Base):
    """Crypto deposit address assigned to a user for a specific network.

    Internal to payments/ module -- not exposed via PaymentServiceProtocol
    models directly. External consumers use DepositAddress dataclass.

    One address per (user_id, network) pair.
    """

    __tablename__ = "crypto_addresses"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Network: TRC20, ERC20, BEP20, PoS.
    network: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Deposit address string (wallet address).
    address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_crypto_addresses_user_network",
            "user_id",
            "network",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<CryptoAddress id={self.id} user={self.user_id} "
            f"network={self.network}>"
        )
