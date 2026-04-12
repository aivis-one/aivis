# =============================================================================
# CBSHOME Backend -- Dashboard Schemas (Sprint 9.2)
# =============================================================================
#
# RESPONSE SCHEMAS:
#   BalanceResponse         -- frozen/confirmed split for a ledger
#   CompanySummaryResponse  -- per-company aggregate in dashboard
#   DashboardSummaryResponse -- full investor dashboard widget
#
# All amounts are in USD cents. current_value_cents is computed from
# the company's current price_per_unit_cents * total_units.
# =============================================================================

from uuid import UUID

from pydantic import BaseModel


class BalanceResponse(BaseModel):
    """Ledger balance split by status."""

    frozen: int = 0
    confirmed: int = 0


class CompanySummaryResponse(BaseModel):
    """Per-company aggregate for the dashboard widget."""

    company_id: UUID
    company_name: str
    logo_url: str | None
    total_units: int
    invested_cents: int
    current_value_cents: int


class DashboardSummaryResponse(BaseModel):
    """Full dashboard summary for the authenticated user."""

    active_balance: BalanceResponse
    passive_balance: BalanceResponse
    total_invested_cents: int
    total_units: int
    current_value_cents: int
    companies_count: int
    companies: list[CompanySummaryResponse]
