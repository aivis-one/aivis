"""payments -- Phase 5 Sprint 5.2 tables

Revision ID: 0007_payments
Revises: 0006_products
Create Date: 2026-04-07 00:00:00.000000

Tables:
  - payments: Incoming investor payments (crypto, bank)
  - crypto_addresses: Per-user crypto deposit addresses (internal)

ALTER:
  - active_ledger.origin_payment_id -> FK payments.id
  - passive_ledger.origin_payment_id -> FK payments.id
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_payments"
down_revision: Union[str, None] = "0006_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create payment tables and add FK constraints on ledger tables."""

    # -------------------------------------------------------------------------
    # payments
    # -------------------------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency",
            sa.String(10),
            server_default="USD",
            nullable=False,
        ),
        sa.Column("payment_type", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "frozen_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "provider_data",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column("origin_payment_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["origin_payment_id"],
            ["payments.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # CHECK constraints.
    op.execute("""
        ALTER TABLE payments
            ADD CONSTRAINT ck_payments_payment_type
                CHECK (payment_type IN ('crypto', 'bank')),
            ADD CONSTRAINT ck_payments_status
                CHECK (status IN ('created', 'frozen', 'confirmed', 'failed', 'reversed'))
    """)

    # Indexes.
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_user_status", "payments", ["user_id", "status"])

    # -------------------------------------------------------------------------
    # crypto_addresses
    # -------------------------------------------------------------------------
    op.create_table(
        "crypto_addresses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("network", sa.String(20), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Unique constraint: one address per user per network.
    op.create_index(
        "uq_crypto_addresses_user_network",
        "crypto_addresses",
        ["user_id", "network"],
        unique=True,
    )

    # -------------------------------------------------------------------------
    # ALTER ledger tables: add FK on origin_payment_id -> payments.id
    # -------------------------------------------------------------------------
    op.create_foreign_key(
        "fk_active_ledger_origin_payment",
        "active_ledger",
        "payments",
        ["origin_payment_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_passive_ledger_origin_payment",
        "passive_ledger",
        "payments",
        ["origin_payment_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Drop payment tables and FK constraints in reverse order."""
    # Remove FK constraints from ledger tables.
    op.drop_constraint(
        "fk_passive_ledger_origin_payment",
        "passive_ledger",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_active_ledger_origin_payment",
        "active_ledger",
        type_="foreignkey",
    )

    # Drop tables.
    op.drop_table("crypto_addresses")
    op.drop_table("payments")
