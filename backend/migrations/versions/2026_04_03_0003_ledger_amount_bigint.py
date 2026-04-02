"""ledger amount bigint -- fix amount_cents Integer to BigInteger

Revision ID: 0003_ledger_amount_bigint
Revises: 0002_auth_indexes
Create Date: 2026-04-03 00:00:00.000000

Phase 0 fix: initial_schema created amount_cents as INTEGER (32-bit,
max ~$21.4M). Models define BigInteger (64-bit, max ~$92T). This
migration aligns the DB column type with the ORM model.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ledger_amount_bigint"
down_revision: Union[str, None] = "0002_auth_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Alter amount_cents from INTEGER to BIGINT in both ledger tables."""
    op.alter_column(
        "active_ledger",
        "amount_cents",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        "passive_ledger",
        "amount_cents",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert amount_cents from BIGINT back to INTEGER."""
    op.alter_column(
        "passive_ledger",
        "amount_cents",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "active_ledger",
        "amount_cents",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=False,
    )
