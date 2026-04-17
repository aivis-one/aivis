"""documents language -- add language column, rebuild uniqueness

Revision ID: 0025_documents_language
Revises: 0024_documents_role_metadata
Create Date: 2026-04-17 01:00:00.000000

Adds per-language versioning. Each legal HTML file belongs to one
locale (en / ru / de / ar); the same `type` may have one row per
language. Users sign the exact copy they read, so the signing row
is always in the user's own locale (or the `en` fallback).

Changes:
  - ADD COLUMN language String(10) NOT NULL DEFAULT 'en'
    Existing rows (e.g. the ones created before this migration) are
    assigned to 'en', which matches the content that used to live
    directly in frontend/public/legal/*.html.
  - DROP old uniqueness (type, version)
  - ADD uniqueness (type, version, language)
  - ADD index (type, language, status) for the onboarding list query
    `WHERE status='active' AND required_for_roles @> [...]`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_documents_language"
down_revision: Union[str, None] = "0024_documents_role_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add language column, rebuild uniqueness, add lookup index."""
    # 1) Add language with a safe default for existing rows.
    op.add_column(
        "documents",
        sa.Column(
            "language",
            sa.String(10),
            nullable=False,
            server_default="en",
        ),
    )

    # 2) Replace uniqueness: (type, version) -> (type, version, language).
    op.drop_constraint(
        "uq_documents_type_version",
        "documents",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_documents_type_version_language",
        "documents",
        ["type", "version", "language"],
    )

    # 3) Index for the onboarding list query.
    op.create_index(
        "ix_documents_type_language_status",
        "documents",
        ["type", "language", "status"],
    )


def downgrade() -> None:
    """Drop the language column, restore old uniqueness."""
    op.drop_index("ix_documents_type_language_status", table_name="documents")
    op.drop_constraint(
        "uq_documents_type_version_language",
        "documents",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_documents_type_version",
        "documents",
        ["type", "version"],
    )
    op.drop_column("documents", "language")
