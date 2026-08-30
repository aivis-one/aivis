"""crypto_webhook_events -- the receiver's deduplication table

THE UNIQUE INDEX IS THE FEATURE, NOT AN OPTIMISATION. The payments
service delivers at-least-once: a restart of its delivery process or an
expired lease re-sends an event that was already handled. Without a
uniqueness constraint on (invoice_id, status) the second delivery would
credit the same payment again, and two deliveries in flight at once
would defeat any SELECT-then-INSERT check written above the database.

NO FOREIGN KEY ON invoice_id OR product_ref, DELIBERATELY. An event can
arrive for an invoice this product has no row for: the service creates
the invoice and commits before answering, so a creation call that timed
out here leaves the service holding an invoice whose product_ref was
never written locally (see the CryptoInvoice docstring). That event must
be recordable -- otherwise every re-delivery of it would be reprocessed
forever -- and a foreign key would reject the row instead.

payment_id IS a foreign key, with ondelete RESTRICT like every other
reference to payments in this schema: the Payment it points at was
created by this very event, so it always exists.

Revision ID: 0048_crypto_webhook_events
Revises: 0047_crypto_invoices
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_crypto_webhook_events"
down_revision: str | None = "0047_crypto_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crypto_webhook_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", sa.UUID(as_uuid=True), nullable=False),
        # No CHECK listing the four statuses: the vocabulary belongs to
        # the service, and a copy welded into a constraint here would
        # turn a status it adds later into a failing INSERT -- exactly
        # the reasoning crypto_invoices.status was created with.
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("product_ref", sa.UUID(as_uuid=True), nullable=False),
        # NULLABLE BECAUSE THE KEY CAN BE ABSENT, NOT BECAUSE THE AMOUNT
        # CAN BE ZERO. The service omits credited_amount_cents entirely
        # when it does not apply; 0 is a legitimate credited amount (a
        # dust transfer). NULL and 0 mean different things in this
        # column and code must not conflate them.
        sa.Column("credited_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("underpaid", sa.Boolean(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column(
            "payment_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "uq_crypto_webhook_events_invoice_status",
        "crypto_webhook_events",
        ["invoice_id", "status"],
        unique=True,
    )
    # Answers "what happened to this invoice" from the product_ref side,
    # which is the identifier a support request will carry.
    op.create_index(
        "ix_crypto_webhook_events_product_ref",
        "crypto_webhook_events",
        ["product_ref"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_crypto_webhook_events_product_ref",
        table_name="crypto_webhook_events",
    )
    op.drop_index(
        "uq_crypto_webhook_events_invoice_status",
        table_name="crypto_webhook_events",
    )
    op.drop_table("crypto_webhook_events")
