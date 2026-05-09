"""company attachments -- Refactor 2 iter 2.2

Revision ID: 0028_company_attachments
Revises: 0027_option_pool_refactor
Create Date: 2026-05-09 00:00:00.000000

Tables:
  - company_attachments: arbitrary binary files (legal docs, presentations,
    patents, ...) attached to a company. Metadata only -- bytes live in
    MinIO under storage_key (R2 §2.2).

Indexes:
  - ix_company_attachments_company_id          -- single-column lookup
  - ix_company_attachments_category            -- single-column lookup
  - ix_company_attachments_company_cat_pub_del -- composite for the main
                                                  investor query (R2 §3.2)
  - ix_company_attachments_company_order       -- composite for ordered
                                                  display (R2 §3.2)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0028_company_attachments"
down_revision: Union[str, None] = "0027_option_pool_refactor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create company_attachments table + indexes."""

    op.create_table(
        "company_attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        # Categorisation.
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        # Display.
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.String(5000), nullable=True),
        # Storage pointer.
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        # Ordering inside (company_id, category) scope.
        sa.Column(
            "order",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        # Visibility flags -- safety-first defaults.
        sa.Column(
            "is_published",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "is_public",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        # Audit.
        sa.Column("created_by", sa.UUID(), nullable=False),
        # Soft-delete.
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        # Timestamps (TimestampMixin).
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["company_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Single-column indexes mirror the model's index=True declarations.
    op.create_index(
        "ix_company_attachments_company_id",
        "company_attachments",
        ["company_id"],
    )
    op.create_index(
        "ix_company_attachments_category",
        "company_attachments",
        ["category"],
    )

    # Composite index for the main investor list query (R2 §3.2):
    #   WHERE company_id = ? AND category = ?
    #     AND is_published = true AND is_deleted = false
    op.create_index(
        "ix_company_attachments_company_cat_pub_del",
        "company_attachments",
        ["company_id", "category", "is_published", "is_deleted"],
    )

    # Composite index for ordered display inside a category (R2 §3.2):
    #   WHERE company_id = ? ORDER BY "order"
    op.create_index(
        "ix_company_attachments_company_order",
        "company_attachments",
        ["company_id", "order"],
    )


def downgrade() -> None:
    """Drop company_attachments table + indexes."""

    op.drop_index(
        "ix_company_attachments_company_order",
        table_name="company_attachments",
    )
    op.drop_index(
        "ix_company_attachments_company_cat_pub_del",
        table_name="company_attachments",
    )
    op.drop_index(
        "ix_company_attachments_category",
        table_name="company_attachments",
    )
    op.drop_index(
        "ix_company_attachments_company_id",
        table_name="company_attachments",
    )
    op.drop_table("company_attachments")
