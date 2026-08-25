# =============================================================================
# AIVIS.ONE Backend -- Posts Schemas (Sprint 9.1, review fixes)
# =============================================================================
#
# Request/response schemas for posts and events endpoints.
#
# SCHEMAS:
#   CreatePostRequest        -- staff creates post (any owner_type/owner_id)
#   UpdatePostRequest        -- staff partial update (PATCH)
#   CreateCompanyPostRequest -- company creates a post about itself
#                              (TASK-30). No owner_type/owner_id (forced
#                              server-side to company/caller's own id) and
#                              no is_banner (site-wide homepage banner
#                              placement stays a staff-only decision --
#                              see company_router.py for the rationale).
#   UpdateCompanyPostRequest -- company partial update of its own post
#                              (PATCH). Same omissions as the create form.
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
#
# VALIDATION (review fixes):
#   - owner_type: Literal["platform", "company"] (Pydantic 422, not service 400)
#   - cover_url, event.url: must start with http:// or https://
#   - tags: max 50 chars per tag
#   - ends_at > starts_at (when both provided)
# =============================================================================

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared validators
# ---------------------------------------------------------------------------


def _validate_url(v: str | None) -> str | None:
    """Validate URL starts with http:// or https://."""
    if v is not None and not v.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    return v


# Tag type with max length constraint.
Tag = Annotated[str, Field(max_length=50)]


# ---------------------------------------------------------------------------
# Post requests
# ---------------------------------------------------------------------------


class CreatePostRequest(BaseModel):
    """Staff creates a post."""

    model_config = ConfigDict(extra="forbid")

    owner_type: Literal["platform", "company"]
    owner_id: UUID | None = Field(
        default=None,
        description="company_profiles.id (required if owner_type=company)",
    )
    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=50000)
    cover_url: str | None = Field(default=None, max_length=2000)
    tags: list[Tag] | None = Field(default=None)
    is_banner: bool = Field(default=False)
    is_published: bool = Field(default=False)

    _validate_cover_url = field_validator("cover_url")(_validate_url)


class UpdatePostRequest(BaseModel):
    """Staff partial update of a post (PATCH)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=50000)
    cover_url: str | None = None
    tags: list[Tag] | None = None
    is_banner: bool | None = None
    is_published: bool | None = None

    _validate_cover_url = field_validator("cover_url")(_validate_url)


class CreateCompanyPostRequest(BaseModel):
    """Company creates a post about itself (TASK-30).

    owner_type is always "company" and owner_id is always the caller's
    own company_id -- both are forced server-side in
    company_router.py, never taken from the client, so a project can
    never create a post for a different owner_id. is_banner is not
    exposed here: a site-wide homepage banner placement is a staff
    editorial decision (see PostListEditor.vue's
    staff.platform.post.bannerBadge), not something a project should
    be able to grant itself -- every company-authored post is created
    with is_banner=False.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1, max_length=50000)
    cover_url: str | None = Field(default=None, max_length=2000)
    tags: list[Tag] | None = Field(default=None)
    is_published: bool = Field(default=False)

    _validate_cover_url = field_validator("cover_url")(_validate_url)


class UpdateCompanyPostRequest(BaseModel):
    """Company partial update (PATCH) of its own post (TASK-30).

    Same field set as CreateCompanyPostRequest minus title/body being
    optional -- no owner_type/owner_id/is_banner. Ownership (the post
    must belong to the caller's own company_id) is enforced in
    service.update_company_post, not by this schema.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1, max_length=50000)
    cover_url: str | None = None
    tags: list[Tag] | None = None
    is_published: bool | None = None

    _validate_cover_url = field_validator("cover_url")(_validate_url)


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

    _validate_cover_url = field_validator("cover_url")(_validate_url)
    _validate_url_field = field_validator("url")(_validate_url)

    @model_validator(mode="after")
    def _check_dates(self) -> "CreateEventRequest":
        """Validate ends_at > starts_at when both provided."""
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


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

    _validate_cover_url = field_validator("cover_url")(_validate_url)
    _validate_url_field = field_validator("url")(_validate_url)

    @model_validator(mode="after")
    def _check_dates(self) -> "UpdateEventRequest":
        """Validate ends_at > starts_at when both provided in update."""
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be after starts_at")
        return self


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
