# =============================================================================
# AIVIS.ONE Backend -- Purchase Model (Sprint 6.1, Refactor 2 iter 2.4,
#                                      H18 P-74 agreement snapshot)
# =============================================================================
#
# Purchase:
#   Immutable record of a product purchase. One Purchase per Transaction
#   returned by the Distribution Engine.
#
# IMMUTABLE:
#   No updated_at. Two declared exceptions, both narrow and named here
#   so neither reads as a violation:
#     - status changes on reversal (pre-existing).
#     - agreement_html / agreement_snapshot_attempts (H18 P-74),
#       written asynchronously after creation by the background sweep
#       below, never by anything on the purchase's own write path.
#       agreement_snapshot_attempts may increment once per failed
#       sweep pass; agreement_html is written at most once -- a
#       populated value is never re-rendered or overwritten (see
#       render_agreement_html's read-time check).
#   Everything else on this row is fixed at INSERT. Reversals create
#   mirror ledger entries, not new Purchase rows.
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
#   PINNING THE ID WAS NEVER ENOUGH ON ITS OWN (H18 P-74): the row
#   behind that id is mutable (Staff can replace a template's body in
#   place) and, per point 1 above, deletable. A person opening their
#   agreement a year later must see the document they signed, not
#   whatever the id currently resolves to -- see agreement_html below,
#   which is the actual fix; the id is kept for the fallback path only.
#
# H18 P-74 -- AGREEMENT HTML SNAPSHOT:
#   agreement_html is the frozen OUTPUT of purchases.agreement_service.
#   render_agreement_html() -- not the template body, the fully
#   rendered document, assets already inlined as data URIs. That is
#   deliberately more than "the input to the renderer": it also
#   survives a change to render_agreement_html itself (an asset-inlining
#   fix, a Jinja upgrade), because the thing a signed agreement must
#   freeze is the document a person actually saw, not its ingredients.
#
#   NOT WRITTEN INLINE AT PURCHASE TIME. A first design snapshotted it
#   synchronously inside engine.write_transactions() -- caught before
#   shipping (H18 report): write_transactions runs under the same
#   per-user pg_advisory_xact_lock submit_kyc takes (purchases/engine.py,
#   step 1), so a MinIO round-trip + Jinja render sitting inside that
#   lock would have blocked the same person's own KYC submission and
#   their own other purchases for as long as rendering took -- the exact
#   defect H17 P-58 removed from KYC uploads, reintroduced here on the
#   same key. The snapshot is instead written by a background sweep
#   (purchases/agreement_worker.py::run_agreement_snapshot_batch,
#   wired in main.py's lifespan) that runs with no lock held at all,
#   strictly after the purchase's own transaction has long since
#   committed.
#
#   NULL means "no snapshot yet, or none could be taken" -- both read
#   identically at render_agreement_html, which falls back to a live
#   render exactly as it did before this pass. This covers every
#   Purchase that predates this column (always NULL, always falls back,
#   unchanged behaviour) without a backfill: backfilling would freeze
#   old agreements against TODAY's template, which is the defect this
#   pass removes, not a fix for it.
#
#   agreement_snapshot_attempts guards the sweep's own SELECT against a
#   row that can never render (a template with a missing declared asset,
#   for instance): without a ceiling that row would occupy a batch slot
#   on every pass forever, the same failure mode named P-27 in the
#   payments sweeper. Once attempts reaches
#   settings.agreement_snapshot_max_attempts the sweep's WHERE clause
#   itself excludes the row -- no separate dead-letter flag, because
#   nothing downstream needs to distinguish "still retrying" from "gave
#   up": read-time behaviour is identical either way.
#
# NO AGENT_ID:
#   Referral information lives in ReferralAttribution (Sprint 7.2).
#   Purchase does not store agent reference.
#
# NO DOCUMENT_ID, NO SEPARATE STORAGE OBJECT:
#   agreement_html above is a column, not a file -- there is still no
#   MinIO object per Purchase, and PDF generation (generate_agreement_pdf)
#   still happens on demand from whichever HTML render_agreement_html
#   returns (the snapshot, or a live render on a NULL one).
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
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

    # H18 P-74: the actual frozen document -- see module docstring for
    # why the id above was never enough on its own. NULL = no snapshot
    # yet (or one could never be taken); render_agreement_html() falls
    # back to a live render in that case, exactly like before this pass.
    agreement_html: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # H18 P-74: failed-snapshot counter for the background sweep's own
    # WHERE clause (module docstring, "P-27" note). Not a retry-timing
    # backoff -- just a ceiling so a permanently unrenderable row stops
    # occupying a batch slot once settings.agreement_snapshot_max_attempts
    # is reached.
    agreement_snapshot_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
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
