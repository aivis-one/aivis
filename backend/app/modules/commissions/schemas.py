# =============================================================================
# CBSHOME Backend -- Commission Schemas (Sprint 7.3, Task 2b Block C)
# =============================================================================
#
# Pydantic models for leaderboard and commission endpoints.
#
# GET /api/v1/agent/leaderboard         -> LeaderboardResponse
# GET /api/v1/agent/commissions/me      -> CommissionListResponse
# GET /api/v1/agent/commissions/summary -> CommissionSummaryResponse
# =============================================================================

from datetime import date, datetime

from pydantic import BaseModel
from uuid import UUID


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


class LeaderboardEntry(BaseModel):
    """Single agent entry in the leaderboard."""

    agent_id: UUID
    agent_name: str
    rank: int
    volume_cents: int
    is_me: bool = False


class LeaderboardResponse(BaseModel):
    """Response for GET /agent/leaderboard."""

    entries: list[LeaderboardEntry]
    snapshot_at: datetime | None = None
    period_start: date


# ---------------------------------------------------------------------------
# Commissions
# ---------------------------------------------------------------------------


class CommissionEntry(BaseModel):
    """Single commission or volume bonus entry."""

    # "commission" or "volume_bonus"
    type: str
    amount_cents: int
    status: str  # frozen | confirmed
    created_at: datetime

    # Commission-specific fields.
    level: int | None = None
    investor_name: str | None = None
    product_name: str | None = None

    # Volume bonus-specific fields.
    period_type: str | None = None
    rank: int | None = None


class CommissionListResponse(BaseModel):
    """Response for GET /agent/commissions/me."""

    items: list[CommissionEntry]
    total: int


class CommissionSummaryResponse(BaseModel):
    """Response for GET /agent/commissions/summary (Task 2b Block C).

    Server-side month-to-date commission aggregate -- replaces the
    dashboard's client-side sum over the first 100 history entries
    (TD-COMMISSION-MONTH-AGG). Statuses frozen+confirmed, reversed
    excluded; "commission:" reason prefix only (volume bonuses are a
    separate concept on the dashboard).
    """

    month_to_date_cents: int
