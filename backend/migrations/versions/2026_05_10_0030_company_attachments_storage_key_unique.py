"""company_attachments.storage_key unique

Revision ID: 2026_05_10_0030
Revises: 2026_05_09_0028
Create Date: 2026-05-10 00:55:00.000000

Round 4 (MINOR-03). The storage_key column was nullable=False from the
2.2 attachments migration but had no uniqueness guarantee. This adds a
unique index so:
  - direct DB pokes that accidentally reuse a key are rejected at write
    time (rather than silently corrupting the MinIO -> DB mapping);
  - a hypothetical UUID4 collision can never produce two attachment
    rows pointing at the same object;
  - reconcile's "broken-direction" sweep stays correct -- one row per
    object, no ambiguous mappings to disambiguate.

The constraint is enforced as a UNIQUE INDEX (not a column-level
UNIQUE) so the downgrade can drop it cleanly without touching the
column itself.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "2026_05_10_0030"
down_revision = "2026_05_09_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_company_attachments_storage_key",
        "company_attachments",
        ["storage_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_company_attachments_storage_key",
        table_name="company_attachments",
    )
