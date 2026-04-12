"""delivery read_at -- add read_at column for read tracking

Revision ID: 0020_delivery_read_at
Revises: 0019_notifications_target_type
Create Date: 2026-04-12 00:00:00.000000

Changes:
  - ADD read_at (nullable timestamp) to notification_deliveries
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_delivery_read_at"
down_revision: Union[str, None] = "0019_notifications_target_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add read_at column to notification_deliveries."""
    op.add_column(
        "notification_deliveries",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove read_at column."""
    op.drop_column("notification_deliveries", "read_at")
