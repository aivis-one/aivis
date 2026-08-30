# =============================================================================
# AIVIS.ONE Backend -- Payment Models (Sprint 5.2)
# =============================================================================
#
# Payment:
#   Incoming payments from investors only. Each payment creates a
#   corresponding active_ledger entry.
#
#   ITS WRITER IS THE WEBHOOK RECEIVER (H8). The stub crypto webhook
#   that used to write it was removed with the rest of that contour and
#   the model was kept writerless for one delivery; crediting an event
#   now creates one again. Crediting past this model was considered and
#   rejected: active_ledger.origin_payment_id is what the reversal chain
#   walks, run_confirmation_batch is the only emitter of the
#   deposit.confirmed notification and it moves Payment rows, and the
#   staff routes and payment history read this table. A balance with no
#   Payment behind it could not be reversed, announced or listed.
#
#   Status lifecycle: created -> frozen -> confirmed (or reversed/failed).
#   See AIVIS-State-Machines.md section 1.
#
#   provider_data is JSONB -- schema depends on payment_type:
#     crypto: {network, to_address, from_address, tx_hash, ...}
#     bank:   {bank_name, iban, swift, bank_reference, ...}
#
# CryptoInvoice:
#   One row per invoice the payments service actually issued. The row
#   id IS the product_ref the service was given, so an incoming event
#   resolves to a user by primary key.
#
#   This table carries what crypto_addresses used to carry and is the
#   only thing that did: the payment -> user_id link. The webhook
#   receiver (H8) resolves product_ref through this table.
#
# CryptoWebhookEvent:
#   One row per event accepted from the payments service, unique on
#   (invoice_id, status). The unique index IS the deduplication the
#   service requires of us -- delivery is at-least-once and a repeat is
#   normal traffic, not a fault.
#
# RULES:
#   - All columns use String (not SAEnum) -- project convention
#   - amount_cents is BigInteger (same as ledger)
#   - provider_data mutations via set_jsonb() only (JSONBMixin)
#   - Payment has updated_at (status changes), unlike immutable ledger
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import UUID as SA_UUID
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
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


class CryptoInvoice(UUIDMixin, Base):
    """One invoice the payments service issued, mirrored locally.

    THE ROW IS WRITTEN AFTER THE SERVICE ANSWERS, AND THE PRODUCT_REF IS
    MINTED BEFORE THE CALL. A uuid4 is generated, handed over as
    ``product_ref``, and becomes this row's primary key once an invoice
    comes back. So the service's ``product_ref`` is always a key here,
    and a lookup from an incoming event is a primary-key read.

    NO ROW IS WRITTEN FOR A CALL THAT FAILED, and that is a correction
    to the original plan rather than a shortcut. Writing an evidence row
    first was meant to make an orphaned invoice -- one the service
    created on a call that then timed out -- traceable back to a user.
    It cannot: the service exposes no lookup by product_ref (its API is
    create / read-by-id / submit-txid and nothing else), so nothing
    could ever be reconciled against such a row. Under the commit rule
    the row would also roll back with the failing request, making the
    state unobservable in the first place -- a column documenting a
    situation that cannot occur. What survives a failed creation is the
    log line carrying the product_ref, which is the honest amount of
    evidence available.

    The orphan itself is harmless rather than merely tolerated: the
    deposit address is static per network, and the service's partial
    unique index on (network, txid) will not let one transfer settle
    against two invoices.

    THIS TABLE CARRIES THE LINK crypto_addresses USED TO CARRY. The old
    contour resolved a payment to its owner through a per-user deposit
    address. Addresses belong to the service now and are static per
    network, so the only remaining route from an incoming payment to a
    user is product_ref -> this row -> user_id.
    """

    __tablename__ = "crypto_invoices"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # The service's own id for this invoice. NOT NULL: the row does not
    # exist until the service has answered with one.
    service_invoice_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        nullable=False,
        unique=True,
    )

    # Canonical service network name (USDT-TRC20 / USDT-ERC20 /
    # USDT-BSC20). Stored as sent, not validated against a local list:
    # which networks are served is the service's fact, and a second copy
    # of it here would drift silently (TOR section 11 p.12).
    network: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    # Snapshot of the address the service issued. The service freezes it
    # onto its own invoice for the same reason: rotating the configured
    # wallet must not move an invoice already shown to a user.
    address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    invoice_amount_cents: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # A CACHE WITH NO AUTHORITY. Holds service invoice statuses only
    # (created / awaiting_confirmations / confirmed / attempts_exhausted
    # / expired / stalled), refreshed from whatever the service last
    # told us. Never holds a status the product invented: a local
    # marker in here would make the column mean two different things
    # and would falsify the sentence above it.
    #
    # NO MONEY DECISION BRANCHES ON THIS COLUMN, EVER. Crediting is
    # driven by the webhook and by the amount inside it, never by a
    # local read of this field. The truth about an invoice lives in the
    # service; this is a copy kept for drawing a screen, and it is
    # structurally behind -- the service's own GET resolves expiry
    # lazily and therefore reports a terminal status before the matching
    # event has been emitted at all (TOR section 8, section 11 p.7).
    #
    # Written here so that whoever writes the crediting path finds a
    # convenient `status == "confirmed"` in their own table and knows,
    # at that moment, not to use it.
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
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
        Index("ix_crypto_invoices_user_network", "user_id", "network"),
    )

    def __repr__(self) -> str:
        return (
            f"<CryptoInvoice id={self.id} user={self.user_id} "
            f"network={self.network} status={self.status}>"
        )


class CryptoWebhookEvent(UUIDMixin, Base):
    """One webhook event the payments service delivered to us.

    THIS TABLE IS THE DEDUPLICATION MECHANISM, NOT A LOG. Delivery is
    at-least-once: the service re-delivers after a restart of its
    delivery process or an expired lease, so the same event arrives
    twice as a matter of course rather than as a fault (TOR section 8).
    The unique index on (invoice_id, status) is what makes a second
    arrival a no-op -- the insert loses, and nothing downstream runs.

    WHY A TABLE AND NOT A COLUMN ON CryptoInvoice. The service emits
    four terminal statuses, and the key being deduplicated is the PAIR,
    not the invoice: `confirmed` and `expired` for one invoice are two
    distinct events that must both be processed. A marker on the
    invoice row would therefore need one column per status, and adding
    a fifth status to the service would mean a migration here rather
    than a row with a new value.

    WHY (invoice_id, status) AND NOT (product_ref, status). Both are
    stable, but invoice_id is the service's own key and the one TOR
    section 8 names as the product's dedup obligation. product_ref is
    stored alongside because it is what resolves to a user, and because
    an event whose product_ref matches nothing local still gets a row
    here: without one, an unknown product_ref would be re-processed on
    every re-delivery for as long as the service keeps trying.

    WHAT IS NOT WRITTEN HERE. An event the receiver refuses with 4xx
    leaves no row: a refused event was not processed, and a row saying
    otherwise would make the retry that follows look like a duplicate.
    The trace for that case is the service's own outbox row going
    `failed` with its last error, which is a query rather than a grep.

    `outcome` records what the event actually caused, so "was this paid,
    and if not why not" is answerable with one SELECT instead of a log
    search.
    """

    __tablename__ = "crypto_webhook_events"

    # The service's invoice id, from the event body. Not a foreign key:
    # crypto_invoices is keyed by product_ref, and an event may arrive
    # for an invoice this product has no row for at all (a creation call
    # that timed out after the service had already committed).
    invoice_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        nullable=False,
    )

    # Service status this event announces: confirmed / expired /
    # attempts_exhausted / stalled. No CHECK constraint listing them,
    # for the same reason crypto_invoices.status has none -- the
    # vocabulary is the service's.
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    # As delivered. Not a foreign key for the same reason as invoice_id:
    # the row it points at may not exist, and that case must be
    # recordable rather than rejected by the database.
    product_ref: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        nullable=False,
    )

    # NULLABLE BECAUSE THE KEY IS ABSENT, NOT BECAUSE IT IS ZERO. The
    # service omits credited_amount_cents entirely when it does not
    # apply, and zero is a legitimate value (a dust transfer credits
    # nothing). NULL here means "the event did not carry the key"; 0
    # means "the event credited nothing". Reading one as the other is
    # exactly the defect this column's nullability exists to prevent.
    credited_amount_cents: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    underpaid: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    # The service's timestamp for the transition, not our receipt time.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # What this event caused here -- see WebhookOutcome.
    outcome: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    # The Payment this event created, when it created one. NULL for
    # every non-crediting outcome.
    payment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # THE DEDUPLICATION ITSELF. Enforced by the database rather than
        # by a SELECT-then-INSERT, because two deliveries of the same
        # event can be in flight at once and a check-then-act would let
        # both through.
        Index(
            "uq_crypto_webhook_events_invoice_status",
            "invoice_id",
            "status",
            unique=True,
        ),
        Index("ix_crypto_webhook_events_product_ref", "product_ref"),
    )

    def __repr__(self) -> str:
        return (
            f"<CryptoWebhookEvent invoice={self.invoice_id} "
            f"status={self.status} outcome={self.outcome}>"
        )
