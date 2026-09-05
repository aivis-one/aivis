"""updated_at must be nullable on the two tables 0050 created

Revision ID: 0052_kyc_timestamps_nullable
Revises: 0051_kyc_approve_explicit
Create Date: 2026-09-05

A SEPARATE REVISION RATHER THAN AN EDIT TO 0050, and that is not a
stylistic preference. 0050 has already run: it is on main and it is
applied to the production database. Alembic will never run it again
there, so a corrected 0050 would fix nothing on any box that has
already migrated while quietly making the file disagree with the
database it produced. Editing an applied migration repairs only the
boxes that do not need repairing.

WHAT WAS WRONG. 0050 declared kyc_documents.updated_at and
kyc_settings.updated_at as NOT NULL with a server default. Every other
table in this tree declares that column nullable -- see 0004 and 0005
-- and the reason is in TimestampMixin (app/core/mixins.py):

    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
    )

Optional, with an onupdate and NO default of either kind. The ORM
therefore SUPPLIES the column on INSERT with an explicit NULL rather
than omitting it, and a server default only fires for a value that was
omitted. So the NOT NULL constraint rejected every insert of a
mixin-bearing row:

    null value in column "updated_at" of relation "kyc_documents"
    violates not-null constraint

Thirty-seven tests failed on it, all of them downstream of one INSERT.
The column is set on the first UPDATE and is NULL until then, which is
exactly what "never modified since creation" should look like.

WHY IT WAS NOT CAUGHT EARLIER. The migration was written by reading the
model's intent rather than the mixin's body, and then checked by reading
both files side by side -- which is how two declarations of the same
column stay disagreeing. Model metadata and migration are now compared
mechanically instead.

DOWNGRADE restores NOT NULL, and will fail if any row has a NULL
updated_at by then -- which is every row that has never been updated.
That is honest rather than convenient: the pre-0052 shape genuinely
cannot hold this table's data, and a downgrade that silently
backfilled timestamps would invent an update that never happened.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_kyc_timestamps_nullable"
down_revision: str | None = "0051_kyc_approve_explicit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("kyc_documents", "kyc_settings"):
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
        # The server default goes too. It could never fire (the ORM
        # always supplies the column) and leaving it would tell the next
        # reader that a fresh row carries a timestamp, which it does
        # not.
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
        )


def downgrade() -> None:
    for table in ("kyc_documents", "kyc_settings"):
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        )
