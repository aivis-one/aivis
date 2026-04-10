"""transactions -- Phase 6 Sprint 6.4

Revision ID: 0012_transactions
Revises: 0011_withdrawals
Create Date: 2026-04-11 00:00:00.000000

Tables:
  - transactions: Immutable financial event log
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012_transactions"
down_revision: Union[str, None] = "0011_withdrawals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create transactions table with indexes and CHECK constraint."""

    op.create_table(
        "transactions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency",
            sa.String(10),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("reference_id", sa.UUID(), nullable=True),
        sa.Column("reference_type", sa.String(30), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Primary query: user history sorted by date.
    op.create_index(
        "ix_transactions_user_created",
        "transactions",
        ["user_id", "created_at"],
    )

    # Lifecycle grouping: all events for one entity.
    op.create_index(
        "ix_transactions_reference",
        "transactions",
        ["reference_id", "reference_type"],
    )

    # Filter by event type.
    op.create_index(
        "ix_transactions_type",
        "transactions",
        ["type"],
    )

    # CHECK constraint on type values.
    op.execute(
        """
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_type
        CHECK (type IN (
            'deposit:received', 'deposit:confirmed', 'deposit:reversed',
            'purchase:completed', 'purchase:gift',
            'installment:tranche_paid', 'installment:completed',
            'installment:defaulted',
            'withdrawal:created', 'withdrawal:confirmed',
            'withdrawal:rejected', 'withdrawal:completed',
            'withdrawal:failed',
            'reversal:completed'
        ))
        """
    )

    # CHECK constraint on reference_type values.
    op.execute(
        """
        ALTER TABLE transactions
        ADD CONSTRAINT ck_transactions_reference_type
        CHECK (reference_type IS NULL OR reference_type IN (
            'payment', 'purchase', 'withdrawal', 'installment_plan'
        ))
        """
    )


def downgrade() -> None:
    """Drop transactions table."""
    op.drop_table("transactions")
