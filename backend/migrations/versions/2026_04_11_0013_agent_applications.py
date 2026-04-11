"""agent_applications -- Phase 7 Sprint 7.1

Revision ID: 0013_agent_applications
Revises: 0012_transactions
Create Date: 2026-04-11 00:00:00.000000

Tables:
  - agent_applications: Agent role application history
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_agent_applications"
down_revision: Union[str, None] = "0012_transactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create agent_applications table with constraints and indexes."""

    op.create_table(
        "agent_applications",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "cooldown_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # -- Indexes --
    op.create_index(
        "ix_agent_applications_user_id",
        "agent_applications",
        ["user_id"],
    )
    op.create_index(
        "ix_agent_applications_status",
        "agent_applications",
        ["status"],
    )

    # -- Partial unique: one pending application per user --
    op.create_index(
        "uq_agent_applications_user_pending",
        "agent_applications",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # -- CHECK constraint on status --
    op.execute("""
        ALTER TABLE agent_applications
        ADD CONSTRAINT ck_agent_applications_status
        CHECK (status IN ('pending', 'approved', 'rejected'))
    """)


def downgrade() -> None:
    """Drop agent_applications table."""
    op.drop_table("agent_applications")
