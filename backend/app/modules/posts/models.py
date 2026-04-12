# =============================================================================
# CBSHOME Backend -- Posts Models (Sprint 9.1)
# =============================================================================
#
# Post:
#   Content entity for platform news and company blogs. owner_type
#   determines scope: platform (system news) or company (blog post
#   on behalf of a company). Staff creates both types.
#
# PostDismiss:
#   Per-user banner dismissal record. Immutable -- once dismissed,
#   the banner stays hidden for that user. CASCADE on both FKs.
#
# Event:
#   Calendar event (webinar, meetup, etc.). Standalone entity,
#   not tied to a specific company. Staff manages CRUD.
#
# SOFT DELETE:
#   Post and Event use is_deleted flag. All queries filter by
#   is_deleted=false. No hard delete from API.
#
# TAGS:
#   Post.tags is a JSONB array of strings. Filtering by tag uses
#   JSONB contains operator.
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import JSONBMixin, TimestampMixin, UUIDMixin
from app.modules.posts.constants import OwnerType


class Post(JSONBMixin, UUIDMixin, TimestampMixin, Base):
    """Platform news or company blog post."""

    __tablename__ = "posts"

    owner_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # NULL for platform posts, company_profiles.id for company posts.
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("company_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    body: Mapped[str] = mapped_column(
        String(50000),
        nullable=False,
    )

    cover_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    # Array of string tags, e.g. ["investment", "growth"].
    tags: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    is_banner: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Staff user who created this post.
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Post id={self.id} owner={self.owner_type} "
            f"title={self.title!r} published={self.is_published}>"
        )


class PostDismiss(UUIDMixin, Base):
    """Per-user banner dismissal -- immutable record."""

    __tablename__ = "post_dismissals"

    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PostDismiss post={self.post_id} user={self.user_id}>"
        )


class Event(UUIDMixin, TimestampMixin, Base):
    """Calendar event (webinar, meetup, etc.)."""

    __tablename__ = "events"

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(5000),
        nullable=True,
    )

    cover_url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    url: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )

    is_published: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    # Staff user who created this event.
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Event id={self.id} title={self.title!r} "
            f"starts_at={self.starts_at}>"
        )
