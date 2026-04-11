"""notifications target_type check

Revision ID: 0019_notifications_target_type
Revises: 0018_notifications_constraints
Create Date: 2026-04-12 00:00:00.000000

Changes:
  - ADD CHECK constraint on notifications.target_type
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0019_notifications_target_type"
down_revision: Union[str, None] = "0018_notifications_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CHECK constraint on target_type."""
    op.create_check_constraint(
        "ck_notifications_target_type",
        "notifications",
        "target_type IN ('user','role','all')",
    )


def downgrade() -> None:
    """Remove CHECK constraint."""
    op.drop_constraint("ck_notifications_target_type", "notifications")
