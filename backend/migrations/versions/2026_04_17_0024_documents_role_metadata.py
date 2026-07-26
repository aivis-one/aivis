"""documents role metadata -- drop content_url/type CHECK, add required_for_roles + content_hash

Revision ID: 0024_documents_role_metadata
Revises: 0023_onboarding_complete
Create Date: 2026-04-17 00:00:00.000000

Changes:
  - DROP CONSTRAINT ck_documents_type. Document types are no longer a
    fixed enum; values come from <meta name="aivis-document-type"> in HTML
    files under frontend/public/legal/.
  - DROP COLUMN content_url. Document bodies live in the frontend as
    static HTML; the backend stores metadata only.
  - ADD COLUMN required_for_roles JSONB NOT NULL DEFAULT '[]'::jsonb.
    Replaces the hard-coded ROLE_REQUIRED_DOCUMENT_TYPES dict in
    documents/constants.py. Seed populates it from
    <meta name="aivis-required-for-roles">.
  - ADD COLUMN content_hash String(64) NOT NULL DEFAULT ''. SHA-256 hex
    digest of the HTML body. Seed compares hashes on every run to detect
    content changes and bump version (old row -> archived, new row ->
    active v+1). Never read through the API -- internal to seed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0024_documents_role_metadata"
down_revision: Union[str, None] = "0023_onboarding_complete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make documents.type free-form, drop body column, add role + hash metadata."""
    # Type is now free-form; seed derives values from HTML metadata.
    op.drop_constraint("ck_documents_type", "documents")

    # Body now lives in frontend/public/legal/*.html, not in the DB.
    op.drop_column("documents", "content_url")

    # List of roles that must sign this document during onboarding.
    op.add_column(
        "documents",
        sa.Column(
            "required_for_roles",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # SHA-256 hex digest of the HTML body; used by seed to detect edits.
    op.add_column(
        "documents",
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    """Restore the previous schema."""
    op.drop_column("documents", "content_hash")
    op.drop_column("documents", "required_for_roles")

    # content_url was NOT NULL; use a temporary server_default so the
    # migration does not fail when downgrading with existing rows.
    op.add_column(
        "documents",
        sa.Column(
            "content_url",
            sa.String(2000),
            nullable=False,
            server_default="",
        ),
    )
    op.alter_column("documents", "content_url", server_default=None)

    op.execute("""
        ALTER TABLE documents
            ADD CONSTRAINT ck_documents_type
                CHECK (type IN (
                    'privacy_policy', 'terms_of_service',
                    'investment_agreement', 'agent_agreement',
                    'company_agreement'
                ))
    """)
