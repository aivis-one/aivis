"""comms recipient snapshot version (H23 P-112)

Revision ID: 0055_comms_snapshot_version
Revises: 0054_purchase_agreement_snapshot
Create Date: 2026-09-25

comms 3.0.0 versions the recipient snapshot: both write paths -- PUT
/api/v1/recipients/{id} and the user_upserted event -- carry `version`,
an integer the product raises with every change of the person, and comms
applies a snapshot only when its version is higher than the stored one.

users.comms_snapshot_version is that counter. It is raised in one place,
core/comms_sync.py::sync_recipient, inside the transaction that changed
the person; users/models.py says why it is not updated_at.

0 means "never sent". No backfill: the server comes up on an empty
database (H23 handoff), and a row that exists before its first snapshot
is exactly the state 0 names.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_comms_snapshot_version"
down_revision: Union[str, None] = "0054_purchase_agreement_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add users.comms_snapshot_version (BigInteger, not null, default 0)."""
    op.add_column(
        "users",
        sa.Column(
            "comms_snapshot_version",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop the counter. comms keeps the versions it stored; a product
    rolled back to before this revision sends none and is refused by
    comms 3.0.0 anyway, so there is nothing to reconcile here."""
    op.drop_column("users", "comms_snapshot_version")
