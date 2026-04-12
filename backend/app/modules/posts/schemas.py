# =============================================================================
# CBSHOME Backend -- Posts Schemas (Sprint 9.1)
# =============================================================================
#
# Request/response schemas for posts and events endpoints.
#
# SCHEMAS:
#   CreatePostRequest    -- staff creates post
#   UpdatePostRequest    -- staff partial update (PATCH)
#   PostResponse         -- single post with is_dismissed flag
#   PostListResponse     -- paginated post list
#   CreateEventRequest   -- staff creates event
#   UpdateEventRequest   -- staff partial update (PATCH)
#   EventResponse        -- single event
#   EventListResponse    -- paginated event list
#
# DESIGN:
#   PostResponse includes is_dismissed (bool) for banner hide logic.
#   Computed per-user via LEFT JOIN on PostDismiss in service.
#   For unauthenticated users, is_dismissed is always false.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Post requests
# ---------------------------------------------------------------------------


class CreatePostRequest(BaseModel):
    """Staff creates a post."""

    model_config = ConfigDict(extra="forbid")

    owner_type: str = Field(
        ...,
        description="platform or company",
    )
    owner_id: UUID | None = Field(
        default=None,
        description="company_profiles.id (required if owner_type=company)",
    )
    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=50000)
    cover_url: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None)
    is_banner: bool = Field(default=False)
    is_published: bool = Field(default=False)


class UpdatePostRequest(BaseModel):
    """Staff partial update of a post (PATCH)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=50000)
    cover_url: str | None = None
    tags: list[str] | None = None
    is_banner: bool | None = None
    is_published: bool | None = None


# ---------------------------------------------------------------------------
# Post responses
# ---------------------------------------------------------------------------


class PostResponse(BaseModel):
    """Single post with dismiss status."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_type: str
    owner_id: UUID | None = None
    title: str
    body: str
    cover_url: str | None = None
    tags: list[str] | None = None
    is_banner: bool
    is_published: bool
    published_at: datetime | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None

    # Computed per-user: True if the user dismissed this banner.
    is_dismissed: bool = False


class PostListResponse(BaseModel):
    """Paginated post list."""

    items: list[PostResponse]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# Event requests
# ---------------------------------------------------------------------------


class CreateEventRequest(BaseModel):
    """Staff creates an event."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    cover_url: str | None = Field(default=None, max_length=2000)
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    is_published: bool = Field(default=False)


class UpdateEventRequest(BaseModel):
    """Staff partial update of an event (PATCH)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    cover_url: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    url: str | None = None
    is_published: bool | None = None


# ---------------------------------------------------------------------------
# Event responses
# ---------------------------------------------------------------------------


class EventResponse(BaseModel):
    """Single event."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None = None
    cover_url: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = None
    url: str | None = None
    is_published: bool
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None


class EventListResponse(BaseModel):
    """Paginated event list."""

    items: list[EventResponse]
    total: int
    page: int
    per_page: int
