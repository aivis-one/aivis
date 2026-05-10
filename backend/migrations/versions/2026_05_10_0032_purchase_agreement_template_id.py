"""purchase_agreement_template_id -- Refactor 2 iter 2.4

Revision ID: 0032_purchase_agreement_template_id
Revises: 0031_company_document_templates
Create Date: 2026-05-10 18:00:00.000000

Adds Purchase.purchase_agreement_template_id (R2 §5.1):
  - Nullable FK to company_document_templates.id, ondelete=SET NULL.
  - Snapshot of the active template at purchase time. NULL in two
    legitimate cases: (a) an archived template row gets cleaned up
    later (SET NULL preserves the Purchase), (b) the template was
    missing at purchase time (broken seed / MinIO outage) -- in which
    case the row is created with NULL and the renderer surfaces 500
    on the agreement endpoint, signalling the broken state to Staff.

  - No index. The column is only read by the agreement render path
    (one Purchase at a time, scanned via the existing id PK).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0032_purchase_agreement_template_id"
down_revision: Union[str, None] = "0031_company_document_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable FK column purchase_agreement_template_id."""
    op.add_column(
        "purchases",
        sa.Column(
            "purchase_agreement_template_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_purchases_agreement_template_id",
        "purchases",
        "company_document_templates",
        ["purchase_agreement_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Drop the FK column."""
    op.drop_constraint(
        "fk_purchases_agreement_template_id",
        "purchases",
        type_="foreignkey",
    )
    op.drop_column("purchases", "purchase_agreement_template_id")
