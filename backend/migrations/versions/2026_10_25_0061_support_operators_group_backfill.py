"""support operators group backfill (H40)

Revision ID: 0061_support_operators_group
Revises: 0060_support_tickets
Create Date: 2026-10-25

NO SCHEMA CHANGE. This migration writes DATA: one outbox event per active
staff profile, declaring that person a member of the comms group
`support_operators` -- the address of the operator signal while a ticket
is not taken ("every operator", service.py::_emit_message_received).

From this revision on the group follows the section roster in ONE place,
service.emit_support_membership: a staff member promoted joins both, a
deactivated one leaves both, with the same `member`. This backfill is the
group's half of what migration 0042 did for the section, for the staff who
existed before the group did.

THE SAME REASONS AS 0042, which this follows to the letter: a migration
rather than a script, so it runs exactly once on every box; every row in
ONE transaction; additive and idempotent in comms (a repeated membership
is a no-op), so a replay duplicates events, not members; no recipient is
created here -- comms retries a membership that arrives before its
recipient. Raw SQL, so the migration does not break when the models
change.

UNLIKE the live emitter, this writes the rows even on a box without a
comms address, exactly as 0042 does: alembic cannot read the product's
settings, and a row nobody ships is the cost of not guessing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0061_support_operators_group"
down_revision: str | None = "0060_support_tickets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors service.SUPPORT_OPERATORS_GROUP -- a migration does not import
# the module it would outlive.
_GROUP_KEY = "support_operators"
_EVENT_TYPE = "group_changed"
_SCHEMA_VERSION = 1


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT user_id FROM staff_profiles WHERE is_active = true")
    ).fetchall()

    if not rows:
        return

    connection.execute(
        sa.text(
            "INSERT INTO outbox_events (event_type, payload) "
            "VALUES (:event_type, CAST(:payload AS jsonb))"
        ),
        [
            {
                "event_type": _EVENT_TYPE,
                "payload": (
                    '{"v": %d, "group_key": "%s", "recipient_id": "%s", '
                    '"member": true}'
                    % (_SCHEMA_VERSION, _GROUP_KEY, row.user_id)
                ),
            }
            for row in rows
        ],
    )


def downgrade() -> None:
    # As 0042: cancel what this queued and has not shipped; what the relay
    # already told comms is not undone by deleting a row here.
    op.execute(
        "DELETE FROM outbox_events "
        f"WHERE event_type = '{_EVENT_TYPE}' AND published_at IS NULL "
        f"AND payload->>'group_key' = '{_GROUP_KEY}'"
    )
