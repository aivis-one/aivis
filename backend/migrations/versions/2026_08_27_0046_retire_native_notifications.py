"""retire native notifications -- drop notifications + notification_deliveries

Revision ID: 0046_retire_native_notifications
Revises: 0045_alembic_version_width
Create Date: 2026-08-27 00:00:00.000000

WHY. TASK-24 batch 3: the comms integration now carries a real emitter
(kyc/service.py::process_webhook -> notification_request, migration-less
since it is a data path, not a schema one). This native module (0017-0020)
predates that integration, was never finished -- create_notification() had
zero call sites anywhere in the backend, 2 of its 4 delivery channels were
permanent stubs, no frontend route ever called it -- and the ruling on
picking up comms was explicit: retire this one once comms carries real
events, never run both at once. Confirmed empty before writing this: both
tables have had no application code path capable of inserting a row since
the day they were created, so there is no data this migration could lose.

Changes:
  - DROP TABLE notification_deliveries (child: drops its own indexes,
    CHECK/UNIQUE constraints and both FKs with it)
  - DROP TABLE notifications (parent: drops its own indexes and CHECK
    constraints with it)

downgrade() recreates the tables in their FINAL shape (i.e. the union of
0017 + 0018 + 0019 + 0020's upgrade() bodies), not 0017's original one --
downgrading through this single step must land on exactly what upgrading
through all four originals produced.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0046_retire_native_notifications"
down_revision: str | None = "0045_alembic_version_width"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the two dead notification tables."""
    op.drop_table("notification_deliveries")
    op.drop_table("notifications")


def downgrade() -> None:
    """Recreate both tables in their final (post-0020) shape."""

    # -- notifications --
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.String(5000), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_value", sa.String(200), nullable=False),
        sa.Column("action_data", JSONB(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expiry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending','processing','sent','partial_sent','failed','expired')",
            name="ck_notifications_status",
        ),
        sa.CheckConstraint(
            "type IN ('system','transaction','commission','news','installment')",
            name="ck_notifications_type",
        ),
        sa.CheckConstraint(
            "target_type IN ('user','role','all')",
            name="ck_notifications_target_type",
        ),
    )
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index(
        "ix_notifications_scheduled_status",
        "notifications",
        ["scheduled_at", "status"],
    )

    # -- notification_deliveries --
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("channel_options", JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending','sent','failed')",
            name="ck_delivery_status",
        ),
        sa.CheckConstraint(
            "channel IN ('telegram','email','push','in_app')",
            name="ck_delivery_channel",
        ),
        sa.UniqueConstraint(
            "notification_id",
            "user_id",
            "channel",
            name="uq_delivery_notification_user_channel",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_notification_id",
        "notification_deliveries",
        ["notification_id"],
    )
    op.create_index(
        "ix_notification_deliveries_user_id",
        "notification_deliveries",
        ["user_id"],
    )
    op.create_index(
        "ix_notification_deliveries_status",
        "notification_deliveries",
        ["status"],
    )
    op.create_index(
        "ix_notification_deliveries_user_status",
        "notification_deliveries",
        ["user_id", "status"],
    )
