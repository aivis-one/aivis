# =============================================================================
# CBSHOME Backend -- Referral Schemas (Sprint 7.2)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
