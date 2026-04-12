"""posts -- Post, PostDismiss, Event tables

Revision ID: 0022_posts
Revises: 0021_delivery_inbox_index
Create Date: 2026-04-12 00:00:00.000000

Changes:
  - CREATE TABLE posts (platform + company content)
  - CREATE TABLE post_dismissals (per-user banner dismissal)
  - CREATE TABLE events (calendar events)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0022_posts"
down_revision: Union[str, None] = "0021_delivery_inbox_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create posts, post_dismissals, events tables."""

    # -- posts --
    op.create_table(
        "posts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_type", sa.String(20), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.String(50000), nullable=False),
        sa.Column("cover_url", sa.String(2000), nullable=True),
        sa.Column("tags", JSONB(), nullable=True),
        sa.Column(
            "is_banner",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "is_published",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["company_profiles.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )

    op.execute("""
        ALTER TABLE posts
            ADD CONSTRAINT ck_posts_owner_type
                CHECK (owner_type IN ('platform', 'company'))
    """)

    op.create_index(
        "ix_posts_feed",
        "posts",
        ["owner_type", "is_published", "is_deleted"],
    )
    op.create_index(
        "ix_posts_created_by",
        "posts",
        ["created_by"],
    )
    op.create_index(
        "ix_posts_owner_id",
        "posts",
        ["owner_id"],
    )

    # -- post_dismissals --
    op.create_table(
        "post_dismissals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "dismissed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_unique_constraint(
        "uq_post_dismissals_post_user",
        "post_dismissals",
        ["post_id", "user_id"],
    )

    # -- events --
    op.create_table(
        "events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.String(5000), nullable=True),
        sa.Column("cover_url", sa.String(2000), nullable=True),
        sa.Column(
            "starts_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("url", sa.String(2000), nullable=True),
        sa.Column(
            "is_published",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )

    op.create_index(
        "ix_events_upcoming",
        "events",
        ["starts_at", "is_published", "is_deleted"],
    )


def downgrade() -> None:
    """Drop posts, post_dismissals, events tables."""
    op.drop_table("events")
    op.drop_table("post_dismissals")
    op.drop_table("posts")
