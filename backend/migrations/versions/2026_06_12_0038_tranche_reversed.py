"""installment_tranches status CHECK + reversed -- tranche-unwind

Revision ID: 0038_tranche_reversed
Revises: 0037_leaderboard_unique
Create Date: 2026-06-12 00:00:00.000000

Tranche-unwind (boss-locked semantics): when the payment that funded a
PAID installment tranche is charged back, the tranche moves to the new
terminal status 'reversed' (the only transition out of 'paid'), its
Purchase flips to REVERSED, and an ACTIVE plan defaults. The tranche
status column is guarded by a DB-level CHECK
(ck_installment_tranches_status, migration 0010) whose value list must
mirror the Python enum -- this migration adds the new value.

Postgres has no ALTER CONSTRAINT for CHECK: drop + re-add. The table
is small and revalidation is cheap (same approach as migration 0036).

DOWNGRADE NOTE: restoring the original list fails if any 'reversed'
rows exist (revalidation rejects them). That is intentional -- a
reversed tranche records a real chargeback; downgrading across this
revision first requires deciding the fate of those rows by hand.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0038_tranche_reversed"
down_revision: Union[str, None] = "0037_leaderboard_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_STATUSES = "'scheduled', 'paid', 'overdue', 'defaulted', 'cancelled'"
_NEW_STATUSES = (
    "'scheduled', 'paid', 'overdue', 'defaulted', 'cancelled', 'reversed'"
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE installment_tranches "
        "DROP CONSTRAINT ck_installment_tranches_status"
    )
    op.execute(
        "ALTER TABLE installment_tranches "
        "ADD CONSTRAINT ck_installment_tranches_status "
        f"CHECK (status IN ({_NEW_STATUSES}))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE installment_tranches "
        "DROP CONSTRAINT ck_installment_tranches_status"
    )
    op.execute(
        "ALTER TABLE installment_tranches "
        "ADD CONSTRAINT ck_installment_tranches_status "
        f"CHECK (status IN ({_OLD_STATUSES}))"
    )
