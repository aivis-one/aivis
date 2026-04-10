"""withdrawals -- Phase 6 Sprint 6.3

Revision ID: 0011_withdrawals
Revises: 0010_installments
Create Date: 2026-04-11 00:00:00.000000

Tables:
  - withdrawals: Withdrawal requests from passive_ledger
Alterations:
  - users: +payout_details JSONB nullable
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0011_withdrawals"
down_revision: Union[str, None] = "0010_installments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create withdrawals table and add payout_details to users."""

    # -----------------------------------------------------------------
    # withdrawals
    # -----------------------------------------------------------------
    op.create_table(
        "withdrawals",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("payout_details_snapshot", JSONB, nullable=False),
        sa.Column("rejection_reason", sa.String(2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes.
    op.create_index(
        "ix_withdrawals_user_id",
        "withdrawals",
        ["user_id"],
    )
    op.create_index(
        "ix_withdrawals_status",
        "withdrawals",
        ["status"],
    )

    # Partial unique index: only one active withdrawal per user.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_withdrawals_user_active
        ON withdrawals (user_id)
        WHERE status IN ('pending', 'confirmed', 'processing')
        """
    )

    # CHECK constraints.
    op.execute(
        """
        ALTER TABLE withdrawals
        ADD CONSTRAINT ck_withdrawals_status
        CHECK (status IN (
            'pending', 'confirmed', 'processing',
            'completed', 'rejected', 'failed'
        ))
        """
    )
    op.execute(
        """
        ALTER TABLE withdrawals
        ADD CONSTRAINT ck_withdrawals_amount_positive
        CHECK (amount_cents > 0)
        """
    )

    # -----------------------------------------------------------------
    # users: add payout_details column
    # -----------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column("payout_details", JSONB, nullable=True),
    )


def downgrade() -> None:
    """Drop withdrawals table and payout_details column."""
    op.drop_column("users", "payout_details")
    op.drop_table("withdrawals")
