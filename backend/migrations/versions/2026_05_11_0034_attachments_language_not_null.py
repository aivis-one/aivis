"""attachments language NOT NULL -- iter 2.4-post mini-fix

Revision ID: 0034_attachments_language_not_null
Revises: 0033_roadmap_extension
Create Date: 2026-05-11 14:00:00.000000

Changes:
  - Backfill: UPDATE company_attachments SET language='en'
    WHERE language IS NULL. NULL previously meant "language-agnostic /
    visible to every locale" (R2 v0.6 §3.6) but the product team
    standardised on English-as-fallback: a document tagged language='en'
    is the universal default, and a future per-locale UI fallback
    surfaces the English row when the user's locale has no match.
    Treating NULL as a semantic distinct from 'en' produced silent
    "documents invisible to non-en locales" bugs in Staff workflows.
  - ALTER COLUMN language -> NOT NULL, server_default='en'. The
    server_default protects against direct DB pokes and reconcile-side
    inserts that pre-date the application's own default; the API layer
    requires language explicitly on create via the Pydantic schema, but
    the column-level default catches every other path.
  - Downgrade reverses NOT NULL + DROPs server_default. Backfill is
    NOT reversed -- there's no way to know which rows were originally
    NULL, and 'en' is a safe terminal value either way.

CHECK constraint:
  - Whitelist `language IN ('en','ru','de','ar')` is enforced at the
    Pydantic edge (AttachmentLanguage Literal). No CHECK on the column
    today; this migration does not add one -- the mini-fix scope is
    nullability only, and adding a CHECK would surprise anyone whose
    inbox already carries 'zh' / 'pt' / etc.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_attachments_language_not_null"
down_revision: Union[str, None] = "0033_roadmap_extension"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill NULLs to 'en', then enforce NOT NULL + DEFAULT 'en'."""
    # 1) Backfill before the NOT NULL switch. Using a server-side UPDATE
    # so the migration is single-statement-safe and works on any row
    # count without paging.
    op.execute(
        "UPDATE company_attachments SET language = 'en' "
        "WHERE language IS NULL"
    )

    # 2) Flip nullable=False and attach server_default='en'. existing_type
    # is required for Alembic's batch_alter_table compatibility (some
    # backends would otherwise drop and recreate the column).
    op.alter_column(
        "company_attachments",
        "language",
        existing_type=sa.String(10),
        nullable=False,
        server_default="en",
    )


def downgrade() -> None:
    """Drop server_default + restore nullable=True. Backfill is NOT undone."""
    op.alter_column(
        "company_attachments",
        "language",
        existing_type=sa.String(10),
        nullable=True,
        server_default=None,
    )
