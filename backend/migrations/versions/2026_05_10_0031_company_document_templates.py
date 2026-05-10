"""company document templates -- Refactor 2 iter 2.3

Revision ID: 0031_company_document_templates
Revises: 0030_storage_key_unique
Create Date: 2026-05-10 12:00:00.000000

Tables:
  - company_document_templates: per-company / platform-default Jinja2
    HTML templates with companion binary assets stored in MinIO under
    storage_prefix (R2 §4.2). Metadata only in Postgres.

    company_id is NULLABLE: NULL = platform default (fallback used by
    every company that hasn't supplied its own), NOT NULL = per-company
    override. The 4-stage fallback in find_active_template() (R2 §4.7)
    walks per-company-locale -> per-company-en -> platform-locale ->
    platform-en.

    created_by is NULLABLE because seed_platform_templates.py inserts
    platform-default rows before any staff user exists.

Constraints:
  - PRIMARY KEY (id)
  - FK company_id -> company_profiles.id  ON DELETE RESTRICT (nullable)
  - FK created_by -> users.id             ON DELETE RESTRICT (nullable)
  - UNIQUE (company_id, kind, language, version) NULLS NOT DISTINCT
      Postgres 15+ semantic so the platform-default series
      (company_id IS NULL) is also versioned uniquely. The stack runs
      Postgres 16, so this is safe.

Indexes:
  - ix_company_document_templates_co_kind_lang_status: composite for
    find_active_template's 4-stage lookup. The leading column is
    nullable, which is what we want -- Postgres uses the index for both
    company_id = :id (per-company stages) and company_id IS NULL
    (platform-default stages).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0031_company_document_templates"
down_revision: Union[str, None] = "0030_storage_key_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create company_document_templates table + composite lookup index."""

    op.create_table(
        "company_document_templates",
        # Identity.
        sa.Column("id", sa.UUID(), nullable=False),
        # Ownership: NULL = platform default, NOT NULL = per-company override.
        sa.Column("company_id", sa.UUID(), nullable=True),
        # Classification (R2 §4.3).
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        # Display.
        sa.Column("title", sa.String(500), nullable=False),
        # Storage pointer + asset list.
        sa.Column("storage_prefix", sa.String(500), nullable=False),
        sa.Column("asset_files", postgresql.JSONB(), nullable=False),
        # Lifecycle.
        sa.Column("status", sa.String(20), nullable=False),
        # Audit. Nullable for seed-installed platform defaults.
        sa.Column("created_by", sa.UUID(), nullable=True),
        # Timestamps (TimestampMixin).
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # FKs.
        sa.ForeignKeyConstraint(
            ["company_id"], ["company_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        # NULLS NOT DISTINCT: PG15+ semantic, required so the platform-
        # default series (company_id IS NULL) cannot accumulate duplicate
        # rows for the same (kind, language, version).
        sa.UniqueConstraint(
            "company_id",
            "kind",
            "language",
            "version",
            name="uq_company_document_templates_co_kind_lang_version",
            postgresql_nulls_not_distinct=True,
        ),
    )

    # Composite lookup index for find_active_template's 4-stage fallback
    # (R2 §4.7). company_id leads -- the index serves both per-company
    # and platform-default branches in a single object.
    op.create_index(
        "ix_company_document_templates_co_kind_lang_status",
        "company_document_templates",
        ["company_id", "kind", "language", "status"],
    )


def downgrade() -> None:
    """Drop the table and its lookup index."""
    op.drop_index(
        "ix_company_document_templates_co_kind_lang_status",
        table_name="company_document_templates",
    )
    op.drop_table("company_document_templates")
