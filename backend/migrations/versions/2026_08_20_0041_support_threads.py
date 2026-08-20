"""support_threads -- T-65, the local pointer to a comms support thread

Revision ID: 0041_support_threads
Revises: 0040_outbox_events
Create Date: 2026-08-20 00:00:00.000000

One row per user, pointing at the comms thread that carries their
support conversation. The model header says why the pointer exists; what
matters here is the shape.

NO SEPARATE INDEX ON user_id, deliberately -- and this is the one thing
in here that looks like an omission next to 0039_fk_indexes, which went
through the tree adding indexes to foreign keys. uq_support_threads_user
is a UNIQUE constraint on that exact column, and PostgreSQL implements it
with a unique index; a second index would be the same b-tree twice, paid
for on every insert. The same holds for uq_support_threads_comms_id,
which is what the ownership lookup reads.

CONSTRAINT NAMES ARE COPIED FROM THE MODEL BYTE FOR BYTE. A mismatch is
not cosmetic: --autogenerate would compare the declared constraint with
the one in the database, find two names, and propose dropping one and
creating the other forever.

ondelete="CASCADE" on the user FK: a deleted user's pointer is not a
record of anything -- the conversation it points at lives in comms and is
that service's to keep or expire. RESTRICT would instead make this table
able to block a user deletion, which is not a veto support has any
business holding.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0041_support_threads"
down_revision: str | None = "0040_outbox_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_threads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("comms_thread_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_support_threads_user"),
        sa.UniqueConstraint(
            "comms_thread_id", name="uq_support_threads_comms_id"
        ),
    )


def downgrade() -> None:
    op.drop_table("support_threads")
