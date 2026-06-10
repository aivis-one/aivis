"""referral metrics foundation -- Task 1 Block A

Revision ID: 0035_referral_metrics
Revises: 0034_attachments_lang_notnull
Create Date: 2026-06-10 00:00:00.000000

Naming note: the revision id is kept under 32 characters because
alembic_version.version_num is VARCHAR(32) by default. Longer ids
truncate-fail on the final UPDATE alembic_version statement.

Backend foundation for per-link referral statistics (clicks /
registrations / purchases). Purchases-per-link are already derivable
from referral_attributions.referral_link_id; this migration adds the
two missing pieces:

Changes:
  - referral_links.click_count BIGINT NOT NULL server_default '0'.
    Raw click counter, incremented atomically by the public
    referral-click endpoint (Block B). server_default='0' backfills
    every existing row without a data migration.
  - users.referred_by_link_id UUID NULL, FK referral_links(id)
    ON DELETE SET NULL, + index. Mirrors the existing referred_by
    pattern (P7-01) but at link granularity: set at registration when
    a valid referral code resolves (Block C), NULL otherwise. The
    index serves the GROUP BY / IN(link_ids) aggregation in
    get_my_links / get_my_stats (Block D).

Historical semantics: existing users keep referred_by_link_id = NULL.
We only know their referring agent (referred_by), not the specific
link, so registration_count for pre-existing links starts at 0 by
design.

Downgrade reverses both changes (drop index, FK, both columns).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_referral_metrics"
down_revision: Union[str, None] = "0034_attachments_lang_notnull"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add click_count to referral_links and referred_by_link_id to users."""
    # 1) Raw click counter. BIGINT to match the project convention for
    # unbounded counters (see 0003_ledger_amount_bigint rationale).
    # server_default='0' covers existing rows -- no backfill needed.
    op.add_column(
        "referral_links",
        sa.Column(
            "click_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )

    # 2) Registration -> link capture. Nullable: NULL means "registered
    # without a valid link code" (organic / platform fallback) or
    # "registered before this migration".
    op.add_column(
        "users",
        sa.Column(
            "referred_by_link_id",
            sa.UUID(),
            nullable=True,
        ),
    )

    # Explicitly named FK so the downgrade can drop it deterministically.
    # ON DELETE SET NULL: deleting a link must not delete or block users.
    op.create_foreign_key(
        "fk_users_referred_by_link_id",
        "users",
        "referral_links",
        ["referred_by_link_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Index for the per-link registration aggregates (Block D):
    # COUNT(*) ... WHERE referred_by_link_id IN (...) GROUP BY referred_by_link_id.
    op.create_index(
        "ix_users_referred_by_link_id",
        "users",
        ["referred_by_link_id"],
    )


def downgrade() -> None:
    """Drop index, FK and both columns."""
    op.drop_index("ix_users_referred_by_link_id", table_name="users")
    op.drop_constraint(
        "fk_users_referred_by_link_id",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "referred_by_link_id")
    op.drop_column("referral_links", "click_count")
