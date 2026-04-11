"""referrals -- Phase 7 Sprint 7.2 tables

Revision ID: 0014_referrals
Revises: 0013_agent_applications
Create Date: 2026-04-11 00:00:00.000000

Tables:
  - referral_links: Agent-owned referral links with unique codes
  - referral_attributions: Purchase-to-referral-link mapping
  - users.referred_by: FK to referring user (default = platform)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_referrals"
down_revision: Union[str, None] = "0013_agent_applications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create referral tables and add referred_by to users."""

    # -------------------------------------------------------------------------
    # referral_links
    # -------------------------------------------------------------------------
    op.create_table(
        "referral_links",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "code",
            sa.String(20),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_referral_links_agent_id",
        "referral_links",
        ["agent_id"],
    )

    # -------------------------------------------------------------------------
    # referral_attributions
    # -------------------------------------------------------------------------
    op.create_table(
        "referral_attributions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "purchase_id",
            sa.UUID(),
            sa.ForeignKey("purchases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "referral_link_id",
            sa.UUID(),
            sa.ForeignKey("referral_links.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_referral_attributions_purchase_id",
        "referral_attributions",
        ["purchase_id"],
    )

    op.create_index(
        "ix_referral_attributions_referral_link_id",
        "referral_attributions",
        ["referral_link_id"],
    )

    # -------------------------------------------------------------------------
    # users.referred_by -- nullable first, backfill, then NOT NULL
    # -------------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "referred_by",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    # Backfill: all existing users -> referred_by = platform user id.
    op.execute("""
        UPDATE users
        SET referred_by = (
            SELECT id FROM users WHERE role = 'platform' LIMIT 1
        )
        WHERE referred_by IS NULL
    """)

    # Now enforce NOT NULL.
    op.alter_column("users", "referred_by", nullable=False)

    op.create_index(
        "ix_users_referred_by",
        "users",
        ["referred_by"],
    )


def downgrade() -> None:
    """Drop referral tables and referred_by column."""
    op.drop_index("ix_users_referred_by", table_name="users")
    op.drop_column("users", "referred_by")
    op.drop_table("referral_attributions")
    op.drop_table("referral_links")
