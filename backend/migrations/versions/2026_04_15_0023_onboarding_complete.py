"""add onboarding_complete step

Revision ID: 0023_onboarding_complete
Revises: 0022_posts
Create Date: 2026-04-15 00:00:00.000000

Changes:
  - ALTER CHECK constraint on users.onboarding_step to include 'onboarding_complete'
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0023_onboarding_complete"
down_revision: Union[str, None] = "0022_posts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'onboarding_complete' to onboarding_step CHECK constraint."""
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_onboarding_step")
    op.execute("""
        ALTER TABLE users
            ADD CONSTRAINT ck_users_onboarding_step
                CHECK (onboarding_step IN (
                    'registered',
                    'email_verified',
                    'profile_complete',
                    'kyc_done',
                    'role_selected',
                    'onboarding_complete'
                ))
    """)


def downgrade() -> None:
    """Remove 'onboarding_complete' from onboarding_step CHECK constraint."""
    op.execute("ALTER TABLE users DROP CONSTRAINT ck_users_onboarding_step")
    op.execute("""
        ALTER TABLE users
            ADD CONSTRAINT ck_users_onboarding_step
                CHECK (onboarding_step IN (
                    'registered',
                    'email_verified',
                    'profile_complete',
                    'kyc_done',
                    'role_selected'
                ))
    """)
