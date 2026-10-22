"""purchases: pending_acceptance status and the source purchase of a bonus row

Revision ID: 0056_gift_pending_acceptance
Revises: 0055_comms_snapshot_version
Create Date: 2026-10-23

TWO CHANGES ON purchases, nothing else.

1. ck_purchases_status is widened from ('active', 'reversed') to also
   admit 'pending_acceptance' and 'cancelled'. A gift granted by staff is
   stored as a purchase in that status and credits nothing -- no ledger
   entry, no pool consumption, not counted in any portfolio figure --
   until the recipient accepts it, which flips it to 'active' and writes
   the entries. 'cancelled' is a pending gift that staff closed before it
   was accepted: still no ledger entry, and not a reversal of real money.

2. purchases.source_purchase_id: nullable uuid, FK to purchases.id
   (ON DELETE SET NULL), indexed. A bonus row written by the engine in the
   same batch as a sale or an instalment tranche carries that sale's id,
   so the sale's agreement can list its own bonus parts without guessing
   by timestamp. NULL for every other row.

NO BACKFILL. Bonus rows that exist already keep NULL: the link cannot be
reconstructed reliably, and NULL is the honest value for "not recorded".

DOWNGRADE. Drops the column and restores the two-value CHECK. Any row left
in 'pending_acceptance' or 'cancelled' would violate the restored CHECK, so the
downgrade first removes such rows: neither credited anything nor has ledger
entries to unwind.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_gift_pending_acceptance"
down_revision: Union[str, None] = "0055_comms_snapshot_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen the status CHECK; add the nullable source_purchase_id."""
    op.execute("ALTER TABLE purchases DROP CONSTRAINT ck_purchases_status")
    op.execute("""
        ALTER TABLE purchases
        ADD CONSTRAINT ck_purchases_status
        CHECK (status IN ('active', 'reversed', 'pending_acceptance', 'cancelled'))
    """)

    op.add_column(
        "purchases",
        sa.Column("source_purchase_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_purchases_source_purchase_id",
        "purchases",
        "purchases",
        ["source_purchase_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_purchases_source_purchase_id",
        "purchases",
        ["source_purchase_id"],
    )


def downgrade() -> None:
    """Drop the column; restore the two-value status CHECK."""
    op.drop_index("ix_purchases_source_purchase_id", table_name="purchases")
    op.drop_constraint(
        "fk_purchases_source_purchase_id", "purchases", type_="foreignkey"
    )
    op.drop_column("purchases", "source_purchase_id")

    # A pending or cancelled gift credited nothing and has no ledger entries;
    # remove such rows so the restored CHECK can be applied.
    op.execute(
        "DELETE FROM purchases "
        "WHERE status IN ('pending_acceptance', 'cancelled')"
    )
    op.execute("ALTER TABLE purchases DROP CONSTRAINT ck_purchases_status")
    op.execute("""
        ALTER TABLE purchases
        ADD CONSTRAINT ck_purchases_status
        CHECK (status IN ('active', 'reversed'))
    """)
