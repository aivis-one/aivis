"""kyc one open application per user -- partial unique index (H17 P-57)

Revision ID: 0053_kyc_one_open_application
Revises: 0052_kyc_timestamps_nullable
Create Date: 2026-09-08

WHAT WAS MISSING. kyc_applications has never had an index or constraint
that stops two rows with status='submitted' existing for the same
user_id. The only thing standing in the way is the
pg_advisory_xact_lock in kyc/service.py:submit_kyc, taken before the
SELECT that checks for an existing open session. That lock covers
exactly one write path -- submit_kyc itself. A seed script, an ops
console, a future provider callback, or a straight INSERT run by hand
takes none of it, and would open a second SUBMITTED row for the same
person without anything in the database noticing. Once kyc_documents
exists (0050), a second open row is also a second, disconnected set of
identity documents nobody will think to associate with the first.

WHY A SEPARATE LAYER, NOT A REPLACEMENT FOR THE LOCK. The lock and this
index answer different questions. The lock makes two concurrent
submit_kyc calls for one user serialise, so the second one reads the
first one's write and is refused with a clear ConflictError
(kyc_already_in_progress) before it ever reaches an INSERT -- a good
user-facing error. This index makes the same situation impossible at
the storage layer for callers that never take the lock at all: for
them the failure is a raw IntegrityError, not a friendly refusal, and
that is by design -- it is a backstop, not a second copy of the
lock's UX. submit_kyc's own lock-protected path never reaches this
index in practice; the two never compete for the same case.

THE PREDICATE. WHERE status = 'submitted' matches, on purpose, the
exact literal submit_kyc's own SELECT checks at the same line the H17
handoff pointed at (kyc/service.py, the SELECT right after the
advisory lock). If that predicate and this one ever read differently,
the index would stop protecting what submit_kyc thinks is protected --
so a change to what "open" means for one has to change both, and this
migration is the second place, named here so the connection is not
lost.

Every other status (approved, rejected, revoked) is deliberately
excluded from the predicate: KYCApplication is a history table by
design (kyc/models.py), and a person legitimately accumulates many
terminal rows over rejections and resubmits. Only "waiting for a
decision" is meant to be unique per person.

ON EXISTING DATA. This installation has no product data (H17
handoff, P-57: "продуктовых данных нет"), so this note records an
assumption rather than a result actually checked against a populated
table. CREATE UNIQUE INDEX is not CONCURRENTLY here and runs inside
the migration's own transaction; on a table that already holds two
'submitted' rows for one user it would fail the migration outright
(duplicate key violates unique constraint) rather than silently admit
the bad state. That failure mode is intentional -- an unresolved
duplicate is a fact to surface at migration time, not to paper over --
but it does mean this migration has only ever been run against an
empty kyc_applications table, and a populated environment inheriting
this revision would need any existing duplicate rows resolved first.

FORM. Mirrors uq_agent_applications_user_pending
(0013_agent_applications.py) -- same shape (partial unique on user_id,
one live status word in the predicate) for the same reason (one open
thing per person, history rows exempt).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0053_kyc_one_open_application"
down_revision: Union[str, None] = "0052_kyc_timestamps_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the partial unique index: one 'submitted' row per user_id."""
    op.create_index(
        "uq_kyc_applications_user_submitted",
        "kyc_applications",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'submitted'"),
    )


def downgrade() -> None:
    """Drop the index.

    Always safe -- dropping a unique index never fails on data,
    unlike narrowing a CHECK constraint (see 0049).
    """
    op.drop_index(
        "uq_kyc_applications_user_submitted",
        table_name="kyc_applications",
    )
