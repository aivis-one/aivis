"""support operator mutes (H40)

Revision ID: 0062_support_operator_mutes
Revises: 0061_support_operators_group
Create Date: 2026-10-25

A table and its backfill. `support_operator_mutes` holds the operators
whose comms category `staff_messages` is still to be muted (owner ruling,
H40: the operator signals replace comms' own msg.support_message ping --
support/mute.py says why). The live writer is
service.emit_support_membership (member=True); the step that carries a
row out is mute.apply_operator_mutes.

THE BACKFILL follows 0061 to the letter, for the same staff: one row per
active staff profile, in this migration's transaction, raw SQL so it does
not break when the models change. Written on a box without comms too --
alembic cannot read the product's settings; the step does not run there,
and a row nobody carries out is the cost of not guessing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062_support_operator_mutes"
down_revision: str | None = "0061_support_operators_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# One row per active staff profile; a replay adds nothing.
BACKFILL_SQL = (
    "INSERT INTO support_operator_mutes (user_id, queued_at, attempts) "
    "SELECT user_id, now(), 0 FROM staff_profiles WHERE is_active = true "
    "ON CONFLICT DO NOTHING"
)


def upgrade() -> None:
    op.create_table(
        "support_operator_mutes",
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_table("support_operator_mutes")
