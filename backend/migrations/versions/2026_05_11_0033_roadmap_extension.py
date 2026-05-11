"""roadmap extension -- iter 2.4 R1 §5

Revision ID: 0033_roadmap_extension
Revises: 0032_purchase_agreement_template_id
Create Date: 2026-05-11 00:30:00.000000

Changes:
  - ADD COLUMN kind String(20) NOT NULL DEFAULT 'milestone'.
    The CHECK constraint enforces enum membership (milestone / event /
    announcement). server_default keeps existing rows on 'milestone'
    and protects against direct DB pokes; the API layer requires kind
    explicitly on create.
  - ADD INDEX ix_company_roadmap_items_kind for filtered list queries.
  - ADD COLUMN cover_storage_key String(1000) NULL -- MinIO key for the
    optional roadmap cover image. Populated by the dedicated Staff
    upload endpoint, never via the create/update body.
  - ADD COLUMN external_url String(2000) NULL -- click-through URL for
    event / announcement kinds.
  - ADD COLUMN post_id UUID NULL, FK posts.id ON DELETE SET NULL.
    Enables an event / announcement to link to a Post; deleting the
    Post nullifies the link instead of cascading to the roadmap row.
  - ADD COLUMN linked_product_id UUID NULL, FK products.id ON DELETE
    SET NULL. Links a milestone or announcement to a specific Product.
  - ADD COLUMN valid_until Date NULL -- expiry for events and
    announcements; service layer rejects valid_until <= target_date
    for events.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_roadmap_extension"
down_revision: Union[str, None] = "0032_purchase_agreement_template_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend company_roadmap_items with R1 §5 fields."""
    # kind: existing rows backfill to 'milestone' via server_default.
    op.add_column(
        "company_roadmap_items",
        sa.Column(
            "kind",
            sa.String(20),
            nullable=False,
            server_default="milestone",
        ),
    )
    op.create_check_constraint(
        "ck_company_roadmap_items_kind",
        "company_roadmap_items",
        "kind IN ('milestone', 'event', 'announcement')",
    )
    op.create_index(
        "ix_company_roadmap_items_kind",
        "company_roadmap_items",
        ["kind"],
    )

    # cover image storage pointer (MinIO key).
    op.add_column(
        "company_roadmap_items",
        sa.Column("cover_storage_key", sa.String(1000), nullable=True),
    )

    # External click-through URL.
    op.add_column(
        "company_roadmap_items",
        sa.Column("external_url", sa.String(2000), nullable=True),
    )

    # post_id FK with ON DELETE SET NULL.
    op.add_column(
        "company_roadmap_items",
        sa.Column("post_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_company_roadmap_items_post_id",
        "company_roadmap_items",
        "posts",
        ["post_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # linked_product_id FK with ON DELETE SET NULL.
    op.add_column(
        "company_roadmap_items",
        sa.Column("linked_product_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_company_roadmap_items_linked_product_id",
        "company_roadmap_items",
        "products",
        ["linked_product_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # valid_until for events / announcements.
    op.add_column(
        "company_roadmap_items",
        sa.Column("valid_until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Reverse 0033."""
    op.drop_column("company_roadmap_items", "valid_until")
    op.drop_constraint(
        "fk_company_roadmap_items_linked_product_id",
        "company_roadmap_items",
        type_="foreignkey",
    )
    op.drop_column("company_roadmap_items", "linked_product_id")
    op.drop_constraint(
        "fk_company_roadmap_items_post_id",
        "company_roadmap_items",
        type_="foreignkey",
    )
    op.drop_column("company_roadmap_items", "post_id")
    op.drop_column("company_roadmap_items", "external_url")
    op.drop_column("company_roadmap_items", "cover_storage_key")
    op.drop_index(
        "ix_company_roadmap_items_kind",
        table_name="company_roadmap_items",
    )
    op.drop_constraint(
        "ck_company_roadmap_items_kind",
        "company_roadmap_items",
        type_="check",
    )
    op.drop_column("company_roadmap_items", "kind")
