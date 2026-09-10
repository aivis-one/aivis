"""purchase agreement html snapshot (H18 P-74)

Revision ID: 0054_purchase_agreement_snapshot
Revises: 0053_kyc_one_open_application
Create Date: 2026-09-09

WHAT PINNING THE TEMPLATE ID NEVER SOLVED. purchases.
purchase_agreement_template_id (0004-era, formalised R2 iter 2.4)
snapshots WHICH template row applied at purchase time, but the row
behind that id is mutable (a company edits its template body in place)
and deletable (ondelete=SET NULL). A document that establishes a
right has to show what was agreed at signing, not what the id
currently resolves to -- see purchases/models.py's module docstring
for the fuller account, including the design this replaced (rendering
synchronously inside engine.write_transactions, rejected because that
function runs under the same per-user pg_advisory_xact_lock
submit_kyc takes, which would have blocked a person's own KYC
submission and their own other purchases for as long as a MinIO
round-trip + Jinja render took).

TWO COLUMNS:
    agreement_html               -- the frozen, fully-rendered
        document (assets already inlined). NULL until the background
        sweep (purchases/agreement_worker.py) fills it in, or forever
        if it never could; render_agreement_html() falls back to a
        live render on NULL exactly as it did before this pass, so
        every Purchase that predates this migration keeps working
        unchanged.
    agreement_snapshot_attempts  -- failed-attempt counter so a
        permanently unrenderable row (a template with a missing
        declared asset, say) drops out of the sweep's own SELECT once
        it reaches settings.agreement_snapshot_max_attempts, instead
        of occupying a batch slot on every pass forever (the P-27
        class of defect, named in the payments sweeper).

NO BACKFILL. Rendering agreement_html for every existing Purchase at
migration time would freeze old agreements against TODAY's template
state -- exactly the defect this pass removes, not a fix for it. This
installation has no purchases yet in any case (H18 handoff), so the
question of existing rows is moot for now, but the decision would be
the same on a populated table: NULL already means "render live" at
read time, which is the correct behaviour for every row this migration
did not create.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_purchase_agreement_snapshot"
down_revision: Union[str, None] = "0053_kyc_one_open_application"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add agreement_html (Text, nullable) and agreement_snapshot_attempts
    (Integer, not null, default 0) to purchases.
    """
    op.add_column(
        "purchases",
        sa.Column("agreement_html", sa.Text(), nullable=True),
    )
    op.add_column(
        "purchases",
        sa.Column(
            "agreement_snapshot_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop both columns. Always safe -- neither is referenced by a
    foreign key or a unique constraint, and dropping them only removes
    a cache, not a fact: purchase_agreement_template_id (unaffected by
    this revision) remains the fallback path for every row.
    """
    op.drop_column("purchases", "agreement_snapshot_attempts")
    op.drop_column("purchases", "agreement_html")
