"""project data in the reader's language: translations and picture variants (H38 P-132)

Revision ID: 0058_project_translations
Revises: 0057_project_media_storage_keys
Create Date: 2026-10-25

English stays in the existing text columns -- the base and the fallback.
Beside them:

    translations    JSONB NOT NULL DEFAULT '{}'
        company_profiles (name, description), products (name, description),
        company_roadmap_items (title, description), posts (title, body).
        {"ru": {"name": "..."}}. A new language is a new key: no migration.
        Validated on write by app/core/i18n.py::normalize_translations.

    media_variants  JSONB NOT NULL DEFAULT '{}'
        company_profiles ({"ru": {"logo": key, "logo_dark": key,
        "cover": key}}), products and company_roadmap_items
        ({"ru": {"cover": key}}). Per-language variants of the pictures;
        the existing key columns stay the common file.

NO DATA MOVES: every row starts with empty maps, which read exactly as
before (English text, common picture).

DOWNGRADE drops the columns; variant objects stay in the storage under
companies/<id>/ and are removed by the seed's reset or by hand.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058_project_translations"
down_revision: Union[str, None] = "0057_project_media_storage_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRANSLATED = ("company_profiles", "products", "company_roadmap_items", "posts")
_VARIANTS = ("company_profiles", "products", "company_roadmap_items")


def _jsonb_column(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )


def upgrade() -> None:
    """Add translations to four tables, media_variants to three."""
    for table in _TRANSLATED:
        op.add_column(table, _jsonb_column("translations"))
    for table in _VARIANTS:
        op.add_column(table, _jsonb_column("media_variants"))


def downgrade() -> None:
    """Drop both columns."""
    for table in _VARIANTS:
        op.drop_column(table, "media_variants")
    for table in _TRANSLATED:
        op.drop_column(table, "translations")
