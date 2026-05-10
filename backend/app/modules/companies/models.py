# =============================================================================
# CBSHOME Backend -- Purchase Model (Sprint 6.1, Refactor 2 iter 2.4)
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
# Refactor 2 iter 2.4 -- TEMPLATE SNAPSHOT (R2 §5.1):
#   purchase_agreement_template_id is the snapshot of the document
#   template active at the moment of purchase. The renderer uses this
#   id to load the historical version of the agreement -- if Staff later
#   uploads a new active template for the same (company, kind, language),
#   historical Purchases keep rendering against their own snapshot.
#
#   NULLABLE for two reasons:
#     1. ondelete=SET NULL keeps Purchase history surviving the removal
#        of an old archived template row (Staff cleanup, seed wipe).
#     2. find_active_template() in companies.service walks a 4-stage
#        fallback (R2 §4.7); platform defaults are guaranteed to be
#        seeded, so in steady state NULL never occurs. If NULL slips
#        through (broken seed / MinIO outage during reconcile), the
#        Purchase still persists (financial transaction > document
#        rendering), and the render-time endpoint surfaces 500 to
#        signal the broken-state to Staff (R2 §5.3).
#
# NO AGENT_ID:
#   Referral information lives in ReferralAttribution (Sprint 7.2).
#   Purchase does not store agent reference.
#
# NO DOCUMENT_ID:
#   The rendered HTML / PDF is generated on-demand from Purchase data
#   plus the template snapshot above. No persistent file storage.
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

    # Refactor 2 iter 2.4: template snapshot (R2 §5.1).
    # NULL = template_missing condition; see module docstring.
    purchase_agreement_template_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("company_document_templates.id", ondelete="SET NULL"),
        nullable=True,
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
