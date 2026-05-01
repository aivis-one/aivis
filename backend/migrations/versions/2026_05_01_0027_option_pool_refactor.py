"""option pool refactor -- Sprint 4.3 (TD-071, Share Pool Refactor)

Revision ID: 0027_option_pool_refactor
Revises: 0026_products_cover_url
Create Date: 2026-05-01 00:00:00.000000

Changes:
  - NEW TABLE: option_pools (equity_percent, total_options, status)
                + partial unique index on (company_id) WHERE status='active'
                + CHECK constraints (status, equity_percent > 0, total_options >= 0)
  - company_profiles: +total_supply BIGINT NOT NULL,
                      +shares_per_option INTEGER NOT NULL
  - products: +pool_id UUID NOT NULL FK -> option_pools(id) RESTRICT
              + rename units -> package_size

Data migration strategy (preserves existing data):
  1. Create option_pools table.
  2. Add company_profiles.total_supply, .shares_per_option as nullable.
  3. Backfill: shares_per_option = 1, total_supply = SUM(products.units) per company.
  4. Lock company_profiles new columns as NOT NULL.
  5. Create one active OptionPool per company with equity_percent=100.0
     and total_options=company.total_supply (covers entire supply -- staff
     can later restructure via the pool admin endpoints in Sprint 4.3 B2).
  6. Add products.pool_id as nullable.
  7. Backfill products.pool_id from the only active pool of the product's
     company.
  8. Lock products.pool_id as NOT NULL, add FK + index.
  9. Rename products.units -> products.package_size.
  10. Add partial unique index `uq_one_active_pool_per_company`.

Downgrade reverses every step except for the data inserted into
option_pools (those rows are simply dropped with the table).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0027_option_pool_refactor"
down_revision: Union[str, None] = "0026_products_cover_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create option_pools, extend companies, repoint products."""

    # -------------------------------------------------------------------------
    # 1. Create option_pools table
    # -------------------------------------------------------------------------
    op.create_table(
        "option_pools",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("equity_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("total_options", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="active",
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
        ALTER TABLE option_pools
            ADD CONSTRAINT ck_option_pools_status
                CHECK (status IN ('active', 'archived'))
    """)
    op.execute("""
        ALTER TABLE option_pools
            ADD CONSTRAINT ck_option_pools_equity_percent_positive
                CHECK (equity_percent > 0)
    """)
    op.execute("""
        ALTER TABLE option_pools
            ADD CONSTRAINT ck_option_pools_total_options_nonneg
                CHECK (total_options >= 0)
    """)
    op.create_index(
        "ix_option_pools_company_id",
        "option_pools",
        ["company_id"],
    )
    op.create_index(
        "ix_option_pools_status",
        "option_pools",
        ["status"],
    )

    # -------------------------------------------------------------------------
    # 2. Add total_supply, shares_per_option to company_profiles (nullable first)
    # -------------------------------------------------------------------------
    op.add_column(
        "company_profiles",
        sa.Column("total_supply", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "company_profiles",
        sa.Column("shares_per_option", sa.Integer(), nullable=True),
    )

    # -------------------------------------------------------------------------
    # 3. Backfill company supply fields
    # -------------------------------------------------------------------------
    # Default: shares_per_option = 1 (one option = one share).
    # total_supply = SUM(products.units) per company. Companies without
    # products get 0 -- staff can later edit via Sprint 4.3 endpoints.
    # NOTE: products.units still exists at this point (rename happens at step 9).
    op.execute("UPDATE company_profiles SET shares_per_option = 1")
    op.execute("""
        UPDATE company_profiles
        SET total_supply = COALESCE(
            (
                SELECT SUM(units)
                FROM products
                WHERE products.company_id = company_profiles.id
            ),
            0
        )
    """)

    # -------------------------------------------------------------------------
    # 4. Lock company supply fields as NOT NULL
    # -------------------------------------------------------------------------
    op.alter_column(
        "company_profiles",
        "total_supply",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "company_profiles",
        "shares_per_option",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # -------------------------------------------------------------------------
    # 5. Create one active OptionPool per existing company
    # -------------------------------------------------------------------------
    # Pool covers the entire supply (equity_percent = 100). Staff can later
    # carve out a smaller equity slice via PATCH /staff/companies/{id}/pool.
    # gen_random_uuid() is built into PostgreSQL 13+ (no extension needed);
    # CBSHOME runs Postgres 16. Other migrations rely on the same builtin.
    op.execute("""
        INSERT INTO option_pools (
            id, company_id, equity_percent, total_options, status, created_at
        )
        SELECT
            gen_random_uuid(),
            cp.id,
            100.0000,
            cp.total_supply,
            'active',
            now()
        FROM company_profiles cp
    """)

    # -------------------------------------------------------------------------
    # 6. Add products.pool_id (nullable first)
    # -------------------------------------------------------------------------
    op.add_column(
        "products",
        sa.Column("pool_id", sa.UUID(), nullable=True),
    )

    # -------------------------------------------------------------------------
    # 7. Backfill products.pool_id from the company's active pool
    # -------------------------------------------------------------------------
    # Each company has exactly one active pool at this point (just created
    # in step 5), so the subquery returns exactly one row per product.
    op.execute("""
        UPDATE products p
        SET pool_id = (
            SELECT op.id
            FROM option_pools op
            WHERE op.company_id = p.company_id
              AND op.status = 'active'
        )
    """)

    # -------------------------------------------------------------------------
    # 8. Lock products.pool_id as NOT NULL, add FK + index
    # -------------------------------------------------------------------------
    op.alter_column(
        "products",
        "pool_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_products_pool_id",
        "products",
        "option_pools",
        ["pool_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_products_pool_id",
        "products",
        ["pool_id"],
    )

    # -------------------------------------------------------------------------
    # 9. Rename products.units -> products.package_size
    # -------------------------------------------------------------------------
    op.alter_column("products", "units", new_column_name="package_size")

    # -------------------------------------------------------------------------
    # 10. Partial unique index: at most one active pool per company
    # -------------------------------------------------------------------------
    # Plain UNIQUE (company_id) would reject archived pools too; we want a
    # company to be able to have one active + N archived pools (future split).
    op.execute("""
        CREATE UNIQUE INDEX uq_one_active_pool_per_company
            ON option_pools (company_id)
            WHERE status = 'active'
    """)


def downgrade() -> None:
    """Reverse the schema changes. Pool data is dropped with the table."""

    # 10. Drop partial unique index.
    op.execute("DROP INDEX IF EXISTS uq_one_active_pool_per_company")

    # 9. Rename package_size back to units.
    op.alter_column("products", "package_size", new_column_name="units")

    # 8. Drop FK + index on products.pool_id.
    op.drop_index("ix_products_pool_id", table_name="products")
    op.drop_constraint("fk_products_pool_id", "products", type_="foreignkey")

    # 6. Drop products.pool_id column.
    op.drop_column("products", "pool_id")

    # 5. Pool rows go away with the table at step 1 below.
    #    Explicit DELETE first to drop dependent FK rows cleanly even
    #    if any were added between steps -- defensive.
    op.execute("DELETE FROM option_pools")

    # 1. Drop option_pools indexes + table.
    op.drop_index("ix_option_pools_status", table_name="option_pools")
    op.drop_index("ix_option_pools_company_id", table_name="option_pools")
    op.drop_table("option_pools")

    # 4 + 2. Drop company supply columns.
    op.drop_column("company_profiles", "shares_per_option")
    op.drop_column("company_profiles", "total_supply")
