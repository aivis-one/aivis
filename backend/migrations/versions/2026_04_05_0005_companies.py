"""companies -- Phase 4 Sprint 4.1 tables

Revision ID: 0005_companies
Revises: 0004_kyc_and_documents
Create Date: 2026-04-05 00:00:00.000000

Tables:
  - company_profiles: Company identity, pricing, distribution config
  - company_price_history: Immutable price change records
  - company_roadmap_items: Ordered roadmap milestones with soft-delete
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_companies"
down_revision: Union[str, None] = "0004_kyc_and_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create company_profiles, company_price_history, company_roadmap_items."""

    # -------------------------------------------------------------------------
    # company_profiles
    # -------------------------------------------------------------------------
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.String(5000), nullable=True),
        sa.Column("logo_url", sa.String(2000), nullable=True),
        sa.Column("cover_url", sa.String(2000), nullable=True),
        sa.Column("promo_video_url", sa.String(2000), nullable=True),
        sa.Column("presentation_url", sa.String(2000), nullable=True),
        sa.Column("price_per_unit_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "distribution_config",
            postgresql.JSONB(),
            nullable=False,
        ),
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
            ["user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_company_profiles_user_id"),
    )
    op.execute("""
        ALTER TABLE company_profiles
            ADD CONSTRAINT ck_company_profiles_status
                CHECK (status IN ('active', 'hidden', 'archived'))
    """)
    op.create_index(
        "ix_company_profiles_user_id",
        "company_profiles",
        ["user_id"],
    )
    op.create_index(
        "ix_company_profiles_status",
        "company_profiles",
        ["status"],
    )

    # -------------------------------------------------------------------------
    # company_price_history
    # -------------------------------------------------------------------------
    op.create_table(
        "company_price_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("price_per_unit_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("changed_by", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["company_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_company_price_history_company_id",
        "company_price_history",
        ["company_id"],
    )

    # -------------------------------------------------------------------------
    # company_roadmap_items
    # -------------------------------------------------------------------------
    op.create_table(
        "company_roadmap_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.String(5000), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default="planned",
            nullable=False,
        ),
        sa.Column(
            "order",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
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
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["company_id"], ["company_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("""
        ALTER TABLE company_roadmap_items
            ADD CONSTRAINT ck_company_roadmap_items_status
                CHECK (status IN ('planned', 'in_progress', 'completed'))
    """)
    op.create_index(
        "ix_company_roadmap_items_company_id",
        "company_roadmap_items",
        ["company_id"],
    )


def downgrade() -> None:
    """Drop company tables in reverse order."""
    op.drop_table("company_roadmap_items")
    op.drop_table("company_price_history")
    op.drop_table("company_profiles")
