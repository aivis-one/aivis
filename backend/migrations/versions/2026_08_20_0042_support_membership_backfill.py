"""support section roster backfill -- T-67

Revision ID: 0042_support_membership_backfill
Revises: 0041_support_threads
Create Date: 2026-08-20 00:00:00.000000

NO SCHEMA CHANGE. This migration writes DATA: one outbox event per
active staff profile, declaring that person a member of the support
section in comms. The relay ships them like any other event.

WHY A MIGRATION RATHER THAN A ONE-OFF SCRIPT: the roster has a sharp
edge. A section with NO declared members is served by EVERY operator
(that is comms' definition, not a transitional state); the moment the
FIRST member is declared, everybody not on the roster stops serving it
-- stops seeing the queue, stops being able to claim, stops being
pinged. So a partial backfill is strictly worse than none: it would
lock out every staff member who happened to be processed later, or not
at all if the run died halfway. Emitting for everyone inside ONE
transaction makes "some are declared" a state that never exists.

WHY IT IS SAFE TO RUN, AND TO RE-RUN. The events are additive
declarations and comms applies them idempotently (a repeated pair is a
no-op there). Re-running this migration is not expected -- alembic runs
it once -- but a restored database that replays it produces duplicate
events, not duplicate members.

WHAT IT DOES NOT DO: create recipients. comms rejects a membership for
someone it has never heard of with a retryable error and the consumer
retries with backoff, so a staff member whose identity sync is lagging
joins the roster a few seconds later rather than being lost. That
ordering is the same one group membership has always had.

Raw SQL rather than the ORM: a migration that imported the models would
break the day those models change, and this one only needs two columns
and a JSON document.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_support_membership_backfill"
down_revision: str | None = "0041_support_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirrors app/modules/support/service.py. Duplicated here on purpose: a
# migration is a historical record and must keep saying what it said on
# the day it ran, even if the constant is renamed later.
_SECTION_KEY = "support"
_SECTION_LABEL = "Support"
_EVENT_TYPE = "section_membership_changed"
_SCHEMA_VERSION = 1


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT user_id FROM staff_profiles WHERE is_active = true"
        )
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
                    '{"v": %d, "section_key": "%s", "section_label": "%s", '
                    '"operator_id": "%s", "member": true}'
                    % (
                        _SCHEMA_VERSION,
                        _SECTION_KEY,
                        _SECTION_LABEL,
                        row.user_id,
                    )
                ),
            }
            for row in rows
        ],
    )


def downgrade() -> None:
    # The events either have been shipped (in which case deleting the
    # rows undoes nothing) or have not (in which case they are pending
    # work nobody asked to cancel). Removing only the UNSENT ones is the
    # honest inverse: it cancels what this migration queued and leaves
    # what the relay already told comms alone.
    op.execute(
        "DELETE FROM outbox_events "
        f"WHERE event_type = '{_EVENT_TYPE}' AND published_at IS NULL"
    )
