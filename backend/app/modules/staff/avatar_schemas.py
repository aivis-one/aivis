# =============================================================================
# AIVIS.ONE Backend -- Avatar Schemas (Sprint 3.2)
# =============================================================================
#
# REQUEST/RESPONSE SCHEMAS:
#   AvatarStartRequest   -- POST /staff/avatar/start {target_user_id}
#   AvatarStartResponse  -- {avatar_session_id, session_token}
#   AvatarSessionResponse -- GET /staff/avatar/active
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AvatarStartRequest(BaseModel):
    """Request to start avatar session."""

    target_user_id: UUID


class AvatarStartResponse(BaseModel):
    """Response after starting avatar session."""

    avatar_session_id: UUID
    session_token: str


class AvatarSessionResponse(BaseModel):
    """Active avatar session info."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    staff_id: UUID
    target_user_id: UUID
    status: str
    ip_address: str
    created_at: datetime
    ended_at: datetime | None = None
