"""outbox_events -- T-62, transactional outbox to comms

Revision ID: 0040_outbox_events
Revises: 0039_fk_indexes
Create Date: 2026-08-20 00:00:00.000000

Creates the table a domain change writes its outgoing event into, in the
same transaction as the change itself.

TWO THINGS IN HERE ARE NOT THE HOUSE STYLE, and both are deliberate:

1. The primary key is BIGSERIAL (BigInteger + Identity), not the UUID
   every other table in this tree uses. The relay publishes strictly in
   id order, so a monotonically increasing integer IS the publication
   order; a random UUID has none and a timestamp is not unique. The
   model header carries the same note.

2. Both indexes are PARTIAL. ix_outbox_events_unpublished covers only
   the pending tail (published_at IS NULL) -- the relay's steady-state
   scan -- instead of the whole ever-growing history.
   ix_outbox_events_pending_redaction covers the opposite predicate,
   which the first index by construction does not, AND carries "not yet
   redacted" as part of that predicate: a row leaves the index the
   moment its payload is redacted, so the index holds only the window
   of rows still awaiting work rather than growing with the table.

INDEX NAMES ARE COPIED FROM THE MODEL BYTE FOR BYTE. A mismatch here is
not cosmetic: Alembic would compare the declared index with the one in
the database, find two different names, and propose creating one and
dropping the other on every --autogenerate, forever.

The relay and the redaction pass it carries arrive in T-63. Nothing
reads this table until then; the DDL below is the whole of T-62's
schema footprint.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0040_outbox_events"
down_revision: str | None = "0039_fk_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # The relay's scan: WHERE published_at IS NULL ORDER BY id.
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["id"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )

    # The redaction pass. Both halves of the predicate are load-bearing
    # -- see the module docstring, and the model, which must state the
    # same predicate in the same words.
    op.create_index(
        "ix_outbox_events_pending_redaction",
        "outbox_events",
        ["published_at"],
        unique=False,
        postgresql_where=sa.text(
            "published_at IS NOT NULL AND payload <> '{\"redacted\": true}'::jsonb"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_pending_redaction", table_name="outbox_events")
    op.drop_index("ix_outbox_events_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")
