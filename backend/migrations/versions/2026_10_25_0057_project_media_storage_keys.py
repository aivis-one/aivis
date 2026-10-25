"""project media in our storage: object keys replace the image URLs (H36 P-131)

Revision ID: 0057_project_media_storage_keys
Revises: 0056_gift_pending_acceptance
Create Date: 2026-10-25

The logo, the cover of a project and the cover of a product were URLs
that staff typed in by hand, so the pictures lived somewhere outside.
By owner decision they are now objects in our storage, and the rows hold
the object KEY; responses carry a presigned link signed from it at answer
time (companies/media.py).

company_profiles:
    DROP logo_url, cover_url
    ADD  logo_storage_key, logo_dark_storage_key (new: the logo for the
         dark theme), cover_storage_key -- VARCHAR(1000) NULL, the width
         of company_roadmap_items.cover_storage_key.
products:
    DROP cover_url
    ADD  cover_storage_key VARCHAR(1000) NULL

promo_video_url, presentation_url and posts.cover_url are untouched.

NO DATA MOVES. The old values are URLs of files that are not in our
storage; there is nothing to convert them into. The pictures are uploaded
again (H37's seeding uploads its own), and the URLs are dropped -- an
accepted loss, recorded in the H36 handoff. No legacy column is kept as a
fallback.

DOWNGRADE restores the three URL columns empty and drops the keys; the
objects stay in the storage.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057_project_media_storage_keys"
down_revision: Union[str, None] = "0056_gift_pending_acceptance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the image URL columns; add the object key columns."""
    op.drop_column("company_profiles", "logo_url")
    op.drop_column("company_profiles", "cover_url")
    op.add_column(
        "company_profiles",
        sa.Column("logo_storage_key", sa.String(1000), nullable=True),
    )
    op.add_column(
        "company_profiles",
        sa.Column("logo_dark_storage_key", sa.String(1000), nullable=True),
    )
    op.add_column(
        "company_profiles",
        sa.Column("cover_storage_key", sa.String(1000), nullable=True),
    )

    op.drop_column("products", "cover_url")
    op.add_column(
        "products",
        sa.Column("cover_storage_key", sa.String(1000), nullable=True),
    )


def downgrade() -> None:
    """Restore the URL columns (empty); drop the key columns."""
    op.drop_column("products", "cover_storage_key")
    op.add_column(
        "products",
        sa.Column("cover_url", sa.String(2000), nullable=True),
    )

    op.drop_column("company_profiles", "cover_storage_key")
    op.drop_column("company_profiles", "logo_dark_storage_key")
    op.drop_column("company_profiles", "logo_storage_key")
    op.add_column(
        "company_profiles",
        sa.Column("cover_url", sa.String(2000), nullable=True),
    )
    op.add_column(
        "company_profiles",
        sa.Column("logo_url", sa.String(2000), nullable=True),
    )
