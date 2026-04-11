"""referrals_td -- Tech debt fixes for Sprint 7.2

Revision ID: 0015_referrals_td
Revises: 0014_referrals
Create Date: 2026-04-11 00:00:00.000000

Changes:
  - referral_attributions: replace index with UNIQUE on purchase_id
  - referral_links: add is_active BOOLEAN NOT NULL DEFAULT true
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_referrals_td"
down_revision: Union[str, None] = "0014_referrals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add UNIQUE constraint and is_active column."""

    # Replace non-unique index with UNIQUE on purchase_id.
    op.drop_index(
        "ix_referral_attributions_purchase_id",
        table_name="referral_attributions",
    )
    op.create_index(
        "uq_referral_attributions_purchase_id",
        "referral_attributions",
        ["purchase_id"],
        unique=True,
    )

    # Add is_active to referral_links.
    op.add_column(
        "referral_links",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    """Revert UNIQUE and is_active."""
    op.drop_column("referral_links", "is_active")

    op.drop_index(
        "uq_referral_attributions_purchase_id",
        table_name="referral_attributions",
    )
    op.create_index(
        "ix_referral_attributions_purchase_id",
        "referral_attributions",
        ["purchase_id"],
    )
