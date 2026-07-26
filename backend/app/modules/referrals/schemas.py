# =============================================================================
# AIVIS.ONE Backend -- Referral Schemas (Sprint 7.2, downline Task 2b)
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


# ---------------------------------------------------------------------------
# Downline (Task 2b Block A)
# ---------------------------------------------------------------------------


class DownlineInvestorEntry(BaseModel):
    """Investor in the agent's downline (commission-mirror levels).

    Level = number of agent hops from the investor up to the
    requesting agent: direct investors are L1, investors under a
    direct sub-agent are L2, one agent deeper -- L3. L4+ are outside
    the 3-level commission area and excluded.

    display_name is MASKED (decision #5): no email, phone or KYC
    status is ever exposed, uniformly across all levels.
    """

    user_id: UUID
    display_name: str
    level: int
    registered_at: datetime
    purchase_volume_cents: int


class DownlineSubAgentEntry(BaseModel):
    """Sub-agent in the agent's downline, agent-hop depth 1..3.

    recruited_investor_count / direct_volume_cents cover only the
    sub-agent's DIRECT investors (decision #4, non-recursive).
    own_purchase_volume_cents is the sub-agent's OWN purchases
    (decision #8): agents are buyers too, and their purchases feed the
    requesting agent's commission exactly like investor purchases --
    without this field the screen would show less volume than the
    agent is actually commissioned on.
    """

    user_id: UUID
    display_name: str
    level: int
    registered_at: datetime
    recruited_investor_count: int
    direct_volume_cents: int
    own_purchase_volume_cents: int


class ReferralDownlineResponse(BaseModel):
    """Response for GET /referrals/downline/me (two collections,
    decision #1 -- not a polymorphic flat tree)."""

    investors: list[DownlineInvestorEntry]
    sub_agents: list[DownlineSubAgentEntry]
