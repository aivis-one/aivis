"""support tickets, the spam bin, a thread per ticket (H40)

Revision ID: 0060_support_tickets
Revises: 0059_support_translation_jobs
Create Date: 2026-10-25

Every appeal through the support form is a ticket: its own comms thread of
kind `ticket` and a row of support_tickets (topic, category, our status,
who took it, a version for compare-and-set). Models: SupportTicket,
SupportSpamTombstone, SupportThreadPurge (app/modules/support/models.py);
writers: app/modules/support/service.py and purge.py.

support_threads:
    DROP uq_support_threads_user -- a person has a thread per ticket now;
    ADD  ix_support_threads_user_id -- the person's threads are still
         looked up by user.
support_tickets:
    one row per ticket thread, keyed by the support_threads row (DEFERRED
    foreign key, see the model).
support_spam_tombstones / support_thread_purges:
    what the spam bin leaves, and the comms threads it still has to delete.

NO DATA MOVES. Every support_threads row that exists before this revision
is a person's one `dm` conversation, and it stays exactly that: a thread
without a ticket is the person's HISTORY (owner ruling) -- read in their
feed, read-only for operators. No ticket is made after the fact.

DOWNGRADE drops the three tables and restores the per-user uniqueness --
which fails, loudly, on a database where somebody has already opened a
ticket (two threads of one person). That is the honest inverse: there is
no single thread to keep.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0060_support_tickets"
down_revision: Union[str, None] = "0059_support_translation_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TOPICS = "'payments', 'withdrawal', 'kyc', 'purchases', 'technical', 'other'"
_CATEGORIES = (
    "'payments', 'withdrawals', 'verification', 'purchases', 'tech', 'other'"
)
_STATUSES = "'open', 'resolved', 'rejected', 'duplicate', 'spam'"


def upgrade() -> None:
    """A thread per ticket; the ticket, tombstone and purge tables."""
    op.drop_constraint("uq_support_threads_user", "support_threads", type_="unique")
    op.create_index("ix_support_threads_user_id", "support_threads", ["user_id"])

    op.create_table(
        "support_tickets",
        sa.Column(
            "support_thread_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "claimed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True,
        ),
        sa.Column(
            "status_changed_at", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("support_thread_id"),
        sa.ForeignKeyConstraint(
            ["support_thread_id"],
            ["support_threads.id"],
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["claimed_by_user_id"], ["users.id"], ondelete="SET NULL",
        ),
        sa.CheckConstraint(f"topic IN ({_TOPICS})", name="ck_support_tickets_topic"),
        sa.CheckConstraint(
            f"category IN ({_CATEGORIES})", name="ck_support_tickets_category",
        ),
        sa.CheckConstraint(
            f"status IN ({_STATUSES})", name="ck_support_tickets_status",
        ),
    )
    op.create_index(
        "ix_support_tickets_created",
        "support_tickets",
        ["created_at", "support_thread_id"],
    )

    op.create_table(
        "support_spam_tombstones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            f"category IN ({_CATEGORIES})",
            name="ck_support_spam_tombstones_category",
        ),
    )
    op.create_index(
        "ix_support_spam_tombstones_appealed",
        "support_spam_tombstones",
        ["appealed_at"],
    )

    op.create_table(
        "support_thread_purges",
        sa.Column(
            "comms_thread_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("comms_thread_id"),
    )


def downgrade() -> None:
    """Drop the three tables; one thread per person again."""
    op.drop_table("support_thread_purges")
    op.drop_index(
        "ix_support_spam_tombstones_appealed", table_name="support_spam_tombstones",
    )
    op.drop_table("support_spam_tombstones")
    op.drop_index("ix_support_tickets_created", table_name="support_tickets")
    op.drop_table("support_tickets")
    op.drop_index("ix_support_threads_user_id", table_name="support_threads")
    op.create_unique_constraint(
        "uq_support_threads_user", "support_threads", ["user_id"],
    )
