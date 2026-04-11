"""notifications constraints -- JSONB fix, CHECK, UNIQUE

Revision ID: 0018_notifications_constraints
Revises: 0017_notifications
Create Date: 2026-04-12 00:00:00.000000

Changes:
  - ALTER action_data and channel_options from JSON to JSONB
  - ADD CHECK constraints on status/type/channel columns
  - ADD UNIQUE constraint on (notification_id, user_id, channel)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0018_notifications_constraints"
down_revision: Union[str, None] = "0017_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix JSONB columns and add constraints."""

    # -- Fix JSON -> JSONB --
    op.alter_column(
        "notifications",
        "action_data",
        existing_type=sa.JSON(),
        type_=JSONB(),
        existing_nullable=True,
    )
    op.alter_column(
        "notification_deliveries",
        "channel_options",
        existing_type=sa.JSON(),
        type_=JSONB(),
        existing_nullable=True,
    )

    # -- CHECK constraints --
    op.create_check_constraint(
        "ck_notifications_status",
        "notifications",
        "status IN ('pending','processing','sent','partial_sent','failed','expired')",
    )
    op.create_check_constraint(
        "ck_notifications_type",
        "notifications",
        "type IN ('system','transaction','commission','news','installment')",
    )
    op.create_check_constraint(
        "ck_delivery_status",
        "notification_deliveries",
        "status IN ('pending','sent','failed')",
    )
    op.create_check_constraint(
        "ck_delivery_channel",
        "notification_deliveries",
        "channel IN ('telegram','email','push','in_app')",
    )

    # -- UNIQUE: prevent duplicate deliveries --
    op.create_unique_constraint(
        "uq_delivery_notification_user_channel",
        "notification_deliveries",
        ["notification_id", "user_id", "channel"],
    )


def downgrade() -> None:
    """Remove constraints and revert JSONB to JSON."""
    op.drop_constraint(
        "uq_delivery_notification_user_channel",
        "notification_deliveries",
        type_="unique",
    )
    op.drop_constraint("ck_delivery_channel", "notification_deliveries")
    op.drop_constraint("ck_delivery_status", "notification_deliveries")
    op.drop_constraint("ck_notifications_type", "notifications")
    op.drop_constraint("ck_notifications_status", "notifications")

    op.alter_column(
        "notification_deliveries",
        "channel_options",
        existing_type=JSONB(),
        type_=sa.JSON(),
        existing_nullable=True,
    )
    op.alter_column(
        "notifications",
        "action_data",
        existing_type=JSONB(),
        type_=sa.JSON(),
        existing_nullable=True,
    )
