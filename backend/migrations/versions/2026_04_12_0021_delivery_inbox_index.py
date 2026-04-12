"""delivery inbox index -- partial composite index for inbox queries

Revision ID: 0021_delivery_inbox_index
Revises: 0020_delivery_read_at
Create Date: 2026-04-12 00:00:00.000000

Changes:
  - ADD partial composite index ix_deliveries_user_inbox
    for inbox patterns: list, unread-count, mark-all-read
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_delivery_inbox_index"
down_revision: Union[str, None] = "0020_delivery_read_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial composite index for inbox queries."""
    op.create_index(
        "ix_deliveries_user_inbox",
        "notification_deliveries",
        ["user_id", "status", "read_at", sa.text("sent_at DESC")],
        postgresql_where=sa.text("status = 'sent'"),
    )


def downgrade() -> None:
    """Remove inbox index."""
    op.drop_index("ix_deliveries_user_inbox", "notification_deliveries")
