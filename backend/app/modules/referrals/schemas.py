# =============================================================================
# CBSHOME Backend -- Referral Schemas (Sprint 7.2, extended Task 1 Block B)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReferralClickRequest(BaseModel):
    """Public referral-click payload (Task 1 Block B).

    Fire-and-forget: the endpoint answers 204 whether or not the code
    matches a link, so this schema is the only validation surface.
    max_length mirrors ReferralLink.code String(20).
    """

    code: str = Field(max_length=20)


class ReferralLinkResponse(BaseModel):
    """Single referral link."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    code: str
    created_at: datetime


class ReferralLinkListResponse(BaseModel):
    """Paginated list of referral links."""

    items: list[ReferralLinkResponse]
    total: int
    page: int
    per_page: int


class ReferralStatsResponse(BaseModel):
    """Agent referral statistics."""

    total_links: int
    total_purchases: int
    total_commission_cents: int
