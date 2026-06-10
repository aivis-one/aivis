# =============================================================================
# CBSHOME Backend -- Referral Schemas (Sprint 7.2)
# =============================================================================

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReferralClickRequest(BaseModel):
    """Public referral-click payload (Task 1 Block B).

    max_length mirrors ReferralLink.code String(20); min_length=1
    rejects empty strings at the framework edge instead of spending a
    no-op UPDATE (STYLE-44-01). Fire-and-forget: the endpoint replies
    204 whether or not the code matches a link.
    """

    code: str = Field(min_length=1, max_length=20)


class ReferralLinkResponse(BaseModel):
    """Single referral link with per-link funnel counters (Task 1 D).

    click_count is the raw counter column; registration_count and
    purchase_count are aggregates computed in get_my_links via two
    batched GROUP BY queries (never per-link queries).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    code: str
    is_active: bool
    click_count: int
    registration_count: int
    purchase_count: int
    created_at: datetime


class ReferralLinkListResponse(BaseModel):
    """Paginated list of referral links."""

    items: list[ReferralLinkResponse]
    total: int
    page: int
    per_page: int


class ReferralStatsResponse(BaseModel):
    """Agent referral statistics (funnel order: links -> clicks ->
    registrations -> purchases -> commission)."""

    total_links: int
    total_clicks: int
    total_registrations: int
    total_purchases: int
    total_commission_cents: int
