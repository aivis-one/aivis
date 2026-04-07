"""payments tx_hash unique index -- Phase 5 Sprint 5.2 fix

Revision ID: 0008_payments_tx_hash_index
Revises: 0007_payments
Create Date: 2026-04-08 00:00:00.000000

Adds partial unique index on provider_data->>'tx_hash' to prevent
duplicate crypto payments at DB level (race condition fix).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008_payments_tx_hash_index"
down_revision: Union[str, None] = "0007_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial unique index on tx_hash in provider_data JSONB."""
    op.execute("""
        CREATE UNIQUE INDEX uq_payments_tx_hash
        ON payments ((provider_data->>'tx_hash'))
        WHERE provider_data->>'tx_hash' IS NOT NULL
    """)


def downgrade() -> None:
    """Drop tx_hash unique index."""
    op.drop_index("uq_payments_tx_hash", table_name="payments")
