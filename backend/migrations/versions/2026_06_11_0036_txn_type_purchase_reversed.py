"""transactions type CHECK + purchase:reversed -- R-2.2

Revision ID: 0036_txn_type_purchase_rev
Revises: 0035_referral_metrics
Create Date: 2026-06-11 00:00:00.000000

R-2.2 introduced TransactionType.PURCHASE_REVERSED ("purchase:reversed"),
written by both the payment-reversal auto-unwind (Block A) and the manual
purchase chargeback endpoint (Block B). The transactions table guards its
type column with a DB-level CHECK (ck_transactions_type, migration 0012)
whose value list must mirror the Python enum -- this migration adds the
new value.

Postgres has no ALTER CONSTRAINT for CHECK: drop + re-add. The table is
small (event log) and revalidation is cheap.

DOWNGRADE NOTE: restoring the pre-R-2.2 list fails if any
"purchase:reversed" rows exist (revalidation rejects them). That is
intentional -- the transaction log is immutable by doctrine, so a
downgrade across this revision first requires deciding the fate of those
rows by hand.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0036_txn_type_purchase_rev"
down_revision: Union[str, None] = "0035_referral_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_TYPES = """
    'deposit:received', 'deposit:confirmed', 'deposit:reversed',
    'purchase:completed', 'purchase:gift',
    'installment:tranche_paid', 'installment:completed',
    'installment:defaulted',
    'withdrawal:created', 'withdrawal:confirmed',
    'withdrawal:rejected', 'withdrawal:completed',
    'withdrawal:failed',
    'reversal:completed'
"""

_NEW_TYPES = """
    'deposit:received', 'deposit:confirmed', 'deposit:reversed',
    'purchase:completed', 'purchase:gift', 'purchase:reversed',
    'installment:tranche_paid', 'installment:completed',
    'installment:defaulted',
    'withdrawal:created', 'withdrawal:confirmed',
    'withdrawal:rejected', 'withdrawal:completed',
    'withdrawal:failed',
    'reversal:completed'
"""


def upgrade() -> None:
    """Re-create ck_transactions_type with purchase:reversed allowed."""
    op.execute(
        "ALTER TABLE transactions DROP CONSTRAINT ck_transactions_type"
    )
    op.execute(
        f"""
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_type
        CHECK (type IN ({_NEW_TYPES}))
        """
    )


def downgrade() -> None:
    """Restore the pre-R-2.2 type list (see DOWNGRADE NOTE)."""
    op.execute(
        "ALTER TABLE transactions DROP CONSTRAINT ck_transactions_type"
    )
    op.execute(
        f"""
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_type
        CHECK (type IN ({_OLD_TYPES}))
        """
    )
