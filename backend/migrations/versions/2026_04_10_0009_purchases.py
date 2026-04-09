"""purchases -- Phase 6 Sprint 6.1 tables

Revision ID: 0009_purchases
Revises: 0008_payments_tx_hash_index
Create Date: 2026-04-10 00:00:00.000000

Tables:
  - purchases: Purchase records (sale, gift, installment_tranche)

Columns added:
  - products.purchase_config: JSONB (nullable, fallback to Company)

Columns dropped:
  - products.gift_units: replaced by purchase_config.bonuses[]
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0009_purchases"
down_revision: Union[str, None] = "0008_payments_tx_hash_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create purchases table, add purchase_config, drop gift_units."""

    # -- 1. Create purchases table --
    op.create_table(
        "purchases",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "investor_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.UUID(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.UUID(),
            sa.ForeignKey("company_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("legal_basis", sa.String(30), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("paid_cents", sa.BigInteger(), nullable=False),
        sa.Column("price_per_unit_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes.
    op.create_index("ix_purchases_investor_id", "purchases", ["investor_id"])
    op.create_index("ix_purchases_product_id", "purchases", ["product_id"])
    op.create_index("ix_purchases_company_id", "purchases", ["company_id"])
    op.create_index("ix_purchases_status", "purchases", ["status"])

    # CHECK constraints via ALTER TABLE.
    op.execute("""
        ALTER TABLE purchases
        ADD CONSTRAINT ck_purchases_legal_basis
        CHECK (legal_basis IN ('sale', 'gift', 'installment_tranche'))
    """)

    op.execute("""
        ALTER TABLE purchases
        ADD CONSTRAINT ck_purchases_status
        CHECK (status IN ('active', 'reversed'))
    """)

    # -- 2. Add purchase_config JSONB to products --
    op.add_column(
        "products",
        sa.Column("purchase_config", JSONB, nullable=True),
    )

    # -- 3. Drop gift_units from products --
    op.drop_column("products", "gift_units")


def downgrade() -> None:
    """Reverse: re-add gift_units, drop purchase_config, drop purchases."""

    # Re-add gift_units.
    op.add_column(
        "products",
        sa.Column(
            "gift_units",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Drop purchase_config.
    op.drop_column("products", "purchase_config")

    # Drop purchases table (constraints dropped automatically).
    op.drop_table("purchases")
