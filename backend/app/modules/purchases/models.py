# =============================================================================
# CBSHOME Backend -- Purchase Model (Sprint 6.1)
# =============================================================================
#
# Purchase:
#   Immutable record of a product purchase. One Purchase per Transaction
#   returned by the Distribution Engine.
#
# IMMUTABLE:
#   No updated_at. Entries are never modified (except status on reversal).
#   Reversals create mirror ledger entries, not new Purchase rows.
#
# PRICE SNAPSHOT:
#   price_per_unit_cents is copied from Product at purchase time.
#   Protects against price changes affecting historical records.
#
# NO AGENT_ID:
#   Referral information lives in ReferralAttribution (Sprint 7.2).
#   Purchase does not store agent reference.
#
# NO DOCUMENT_ID:
#   Purchase documents are generated on-demand from Purchase data.
#   No persistent PDF storage needed.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import UUIDMixin
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus


class Purchase(UUIDMixin, Base):
    """Immutable record of a product purchase or gift allocation."""

    __tablename__ = "purchases"

    investor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Denormalized for fast queries without JOIN to products.
    company_id: Mapped[UUID] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Legal classification of this purchase record.
    legal_basis: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Number of units (shares) acquired.
    units: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Amount paid in cents. 0 for gift allocations.
    paid_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Price snapshot at purchase time.
    price_per_unit_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Lifecycle status.
    status: Mapped[str] = mapped_column(
        String(20),
        default=PurchaseStatus.ACTIVE,
        server_default=PurchaseStatus.ACTIVE.value,
        nullable=False,
        index=True,
    )

    # Immutable timestamp -- no updated_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Purchase id={self.id} investor={self.investor_id} "
            f"units={self.units} paid={self.paid_cents} "
            f"basis={self.legal_basis} status={self.status}>"
        )
