# =============================================================================
# AIVIS.ONE Backend -- Agent Application Schemas (Sprint 7.1)
# =============================================================================
#
# AgentApplicationResponse:  returned after POST and in GET /me list
# AgentApplicationListResponse:  paginated list wrapper
# RejectRequest:  body for staff reject endpoint
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AgentApplicationResponse(BaseModel):
    """Single agent application record."""

    id: UUID
    user_id: UUID
    status: str
    rejection_reason: str | None = None
    cooldown_until: datetime | None = None
    reviewed_at: datetime | None = None
    reviewed_by: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentApplicationListResponse(BaseModel):
    """Paginated list of agent applications."""

    items: list[AgentApplicationResponse]
    total: int


class RejectRequest(BaseModel):
    """Body for rejecting an agent application."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Reason for rejection (required)",
    )
