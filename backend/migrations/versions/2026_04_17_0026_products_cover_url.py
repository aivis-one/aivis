"""products cover_url -- Phase F4 Sprint F4.1 storefront denormalisation

Revision ID: 0026_products_cover_url
Revises: 0025_documents_language
Create Date: 2026-04-17 02:00:00.000000

Changes:
  - ADD COLUMN cover_url VARCHAR(2000) NULL to products.
    Nullable: when unset the storefront falls back to the owning company's
    logo/cover, and finally to a placeholder icon on the client.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_products_cover_url"
down_revision: Union[str, None] = "0025_documents_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cover_url column."""
    op.add_column(
        "products",
        sa.Column("cover_url", sa.String(2000), nullable=True),
    )


def downgrade() -> None:
    """Drop cover_url column."""
    op.drop_column("products", "cover_url")
