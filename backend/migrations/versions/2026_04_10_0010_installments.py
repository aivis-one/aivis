"""installment plans -- Phase 6 Sprint 6.2 tables

Revision ID: 0010_installments
Revises: 0009_purchases
Create Date: 2026-04-10 00:00:00.000000

Tables:
  - installment_plans: Active installment plans for investors
  - installment_tranches: Individual tranche payments within plans
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010_installments"
down_revision: Union[str, None] = "0009_purchases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create installment_plans and installment_tranches tables."""

    # -----------------------------------------------------------------
    # installment_plans
    # -----------------------------------------------------------------
    op.create_table(
        "installment_plans",
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
            "product_installment_id",
            sa.UUID(),
            sa.ForeignKey("product_installments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.UUID(),
            sa.ForeignKey("company_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("plan_config_snapshot", JSONB, nullable=False),
        sa.Column("total_price_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False),
        sa.Column("price_per_unit_cents", sa.BigInteger(), nullable=False),
        # Agent fields -- nullable stubs for Sprint 7.x.
        sa.Column("referral_link_id", sa.UUID(), nullable=True),
        sa.Column(
            "agent_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
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
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "defaulted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Indexes.
    op.create_index(
        "ix_installment_plans_investor_id",
        "installment_plans",
        ["investor_id"],
    )
    op.create_index(
        "ix_installment_plans_product_id",
        "installment_plans",
        ["product_id"],
    )
    op.create_index(
        "ix_installment_plans_company_id",
        "installment_plans",
        ["company_id"],
    )
    op.create_index(
        "ix_installment_plans_status",
        "installment_plans",
        ["status"],
    )

    # CHECK constraints.
    op.execute("""
        ALTER TABLE installment_plans
        ADD CONSTRAINT ck_installment_plans_status
        CHECK (status IN ('active', 'completed', 'defaulted', 'cancelled'))
    """)

    op.execute("""
        ALTER TABLE installment_plans
        ADD CONSTRAINT ck_installment_plans_total_price_positive
        CHECK (total_price_cents > 0)
    """)

    op.execute("""
        ALTER TABLE installment_plans
        ADD CONSTRAINT ck_installment_plans_total_units_positive
        CHECK (total_units > 0)
    """)

    # -----------------------------------------------------------------
    # installment_tranches
    # -----------------------------------------------------------------
    op.create_table(
        "installment_tranches",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.UUID(),
            sa.ForeignKey("installment_plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("units_unlocked", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "purchase_id",
            sa.UUID(),
            sa.ForeignKey("purchases.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes.
    op.create_index(
        "ix_installment_tranches_plan_id",
        "installment_tranches",
        ["plan_id"],
    )
    op.create_index(
        "ix_installment_tranches_due_date",
        "installment_tranches",
        ["due_date"],
    )
    op.create_index(
        "ix_installment_tranches_status",
        "installment_tranches",
        ["status"],
    )

    # CHECK constraints.
    op.execute("""
        ALTER TABLE installment_tranches
        ADD CONSTRAINT ck_installment_tranches_status
        CHECK (status IN ('scheduled', 'paid', 'overdue', 'defaulted', 'cancelled'))
    """)

    op.execute("""
        ALTER TABLE installment_tranches
        ADD CONSTRAINT ck_installment_tranches_number_positive
        CHECK (number > 0)
    """)

    op.execute("""
        ALTER TABLE installment_tranches
        ADD CONSTRAINT ck_installment_tranches_amount_positive
        CHECK (amount_cents > 0)
    """)

    op.execute("""
        ALTER TABLE installment_tranches
        ADD CONSTRAINT ck_installment_tranches_units_positive
        CHECK (units_unlocked > 0)
    """)

    # Unique constraint: one tranche number per plan.
    op.create_unique_constraint(
        "uq_installment_tranches_plan_number",
        "installment_tranches",
        ["plan_id", "number"],
    )


def downgrade() -> None:
    """Drop installment tables."""
    op.drop_table("installment_tranches")
    op.drop_table("installment_plans")
