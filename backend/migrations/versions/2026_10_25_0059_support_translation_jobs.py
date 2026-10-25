"""support translation jobs and the comms changes-feed cursor (H39 P-129)

Revision ID: 0059_support_translation_jobs
Revises: 0058_project_translations
Create Date: 2026-10-25

Support messages are translated through the comms llm channel, and the
result is written next to the message as a comms variant (comms
deploy/INTEGRATION.md sections 11-12). Models: SupportTranslationJob
(app/modules/support/models.py) and CommsFeedCursor
(app/core/events/models.py); writers: app/modules/support/translation.py
and app/core/comms_listener.py.

support_translation_jobs:
    the product's queue of translation jobs -- one row per attempt of one
    message into one language. NO MESSAGE TEXT AND NO TRANSLATION: both
    live in comms. job_key unique (the listener finds the row by it);
    (comms_message_id, locale, attempt) unique (two feed reads catching
    up the same message queue one job).
comms_feed_cursors:
    where the comms push listener stopped in comms' changes feed, one
    row per consumer.

NO DATA MOVES: two new tables. Messages written before this revision get
their translations when a feed that shows them is read (the catch-up in
translation.py), not here.

DOWNGRADE drops both tables; the variants already written stay in comms.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0059_support_translation_jobs"
down_revision: Union[str, None] = "0058_project_translations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the translation queue and the feed cursor."""
    op.create_table(
        "support_translation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "support_thread_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "comms_message_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("job_key", sa.String(200), nullable=False),
        sa.Column(
            "request_written_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column(
            "user_notified_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["support_thread_id"], ["support_threads.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("job_key", name="uq_support_translation_jobs_key"),
        sa.UniqueConstraint(
            "comms_message_id", "locale", "attempt",
            name="uq_support_translation_jobs_attempt",
        ),
        sa.CheckConstraint(
            "direction IN ('to_support', 'to_user')",
            name="ck_support_translation_jobs_direction",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN "
            "('variant', 'not_needed', 'declined', 'failed', 'retried')",
            name="ck_support_translation_jobs_outcome",
        ),
        sa.CheckConstraint(
            "attempt >= 1", name="ck_support_translation_jobs_attempt",
        ),
    )
    op.create_index(
        "ix_support_translation_jobs_support_thread_id",
        "support_translation_jobs",
        ["support_thread_id"],
    )
    op.create_table(
        "comms_feed_cursors",
        sa.Column("consumer", sa.String(64), nullable=False),
        sa.Column("cursor", sa.String(2048), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("consumer"),
    )


def downgrade() -> None:
    """Drop both tables."""
    op.drop_table("comms_feed_cursors")
    op.drop_index(
        "ix_support_translation_jobs_support_thread_id",
        table_name="support_translation_jobs",
    )
    op.drop_table("support_translation_jobs")
