"""auth indexes -- functional unique indexes on credentials JSONB

Revision ID: 0002_auth_indexes
Revises: 0001_initial_schema
Create Date: 2026-04-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_auth_indexes"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create partial unique indexes for email and telegram auth lookup.

    Functional indexes on JSONB fields allow fast lookup + uniqueness
    without dedicated columns. NULL-safe: partial WHERE clause ensures
    only rows with the relevant credential are indexed.
    """
    # Email auth: unique by email address (case-sensitive, normalized
    # to lowercase at application level before insert).
    op.execute("""
        CREATE UNIQUE INDEX ix_users_email
            ON users ((credentials->'email'->>'email'))
            WHERE credentials->'email'->>'email' IS NOT NULL
    """)

    # Telegram auth: unique by telegram user id (cast to bigint
    # for proper numeric comparison and compact index).
    op.execute("""
        CREATE UNIQUE INDEX ix_users_telegram_id
            ON users (((credentials->'telegram'->>'id')::bigint))
            WHERE credentials->'telegram'->>'id' IS NOT NULL
    """)


def downgrade() -> None:
    """Drop auth indexes."""
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
