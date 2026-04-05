"""products -- Phase 4 Sprint 4.2 tables

Revision ID: 0006_products
Revises: 0005_companies
Create Date: 2026-04-05 00:00:00.000000

Tables:
  - products: Investment packages belonging to companies
  - product_installments: Installment plan templates with plan_config JSONB
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_products"
down_revision: Union[str, None] = "0005_companies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create products and product_installments tables."""

    # -------------------------------------------------------------------------
    # products
    # -------------------------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.String(5000), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column(
            "gift_units",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("price_per_unit_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="hidden",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"], ["company_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("""
        ALTER TABLE products
            ADD CONSTRAINT ck_products_status
                CHECK (status IN ('active', 'hidden', 'archived'))
    """)
    op.create_index("ix_products_company_id", "products", ["company_id"])
    op.create_index("ix_products_status", "products", ["status"])

    # -------------------------------------------------------------------------
    # product_installments
    # -------------------------------------------------------------------------
    op.create_table(
        "product_installments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("plan_config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_installments_product_id",
        "product_installments",
        ["product_id"],
    )


def downgrade() -> None:
    """Drop product tables in reverse order."""
    op.drop_table("product_installments")
    op.drop_table("products")
