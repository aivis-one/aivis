# =============================================================================
# CBSHOME Backend -- Document Schemas (Sprint 2.2)
# =============================================================================
#
# Pydantic models for document endpoints.
#
# DocumentResponse:      returned by all document endpoints
# DocumentCreateRequest: staff creates a new document
# DocumentUpdateRequest: staff updates document (partial, exclude_unset)
# DocumentSigningResponse: returned after user signs a document
#
# CONTENT_URL VALIDATION:
#   Only https:// URLs are accepted to prevent XSS (javascript:) and
#   LFI (file://) attacks when frontend renders the URL.
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DocumentResponse(BaseModel):
    """Document representation in API responses."""

    id: UUID
    type: str
    version: int
    title: str
    content_url: str
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None
    is_signed: bool | None = None

    model_config = {"from_attributes": True}


class DocumentCreateRequest(BaseModel):
    """Staff creates a new document."""

    type: str = Field(
        ...,
        description="Document type (privacy_policy, terms_of_service, etc.)",
    )
    title: str = Field(..., min_length=1, max_length=500)
    content_url: str = Field(..., min_length=1, max_length=2000)
    version: int = Field(default=1, ge=1)

    @field_validator("content_url")
    @classmethod
    def validate_content_url(cls, v: str) -> str:
        """Ensure content_url uses https:// scheme."""
        if not v.startswith("https://"):
            raise ValueError("content_url must start with https://")
        return v


class DocumentUpdateRequest(BaseModel):
    """Staff updates a document (partial update).

    Only provided fields are applied (exclude_unset in service).
    Status changes are validated against the state machine.
    """

    title: str | None = Field(default=None, min_length=1, max_length=500)
    content_url: str | None = Field(default=None, min_length=1, max_length=2000)
    status: str | None = Field(default=None)

    @field_validator("content_url")
    @classmethod
    def validate_content_url(cls, v: str | None) -> str | None:
        """Ensure content_url uses https:// scheme (when provided)."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("content_url must start with https://")
        return v


class DocumentSigningResponse(BaseModel):
    """Response after user signs a document."""

    id: UUID
    document_id: UUID
    signed_at: datetime

    model_config = {"from_attributes": True}
