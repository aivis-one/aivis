# =============================================================================
# CBSHOME Backend -- Dashboard Service (Sprint 9.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   get_dashboard_summary() -- aggregated data for the main screen widget
#
# QUERIES:
#   1. Active/passive balance via ledgers/service (reuse existing)
#   2. Purchase aggregates: JOIN purchases + company_profiles, GROUP BY
#      company_id. Single query returns per-company totals + current price.
#
# COMMIT RULE (P-01):
#   Service never commits. Read-only queries via get_db_reader.
# =============================================================================

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import CompanyProfile
from app.modules.dashboard.schemas import (
    BalanceResponse,
    CompanySummaryResponse,
    DashboardSummaryResponse,
)
from app.modules.ledgers.service import get_active_balance, get_passive_balance
from app.modules.purchases.constants import PurchaseStatus
from app.modules.purchases.models import Purchase


async def get_dashboard_summary(
    user_id: UUID,
    session: AsyncSession,
) -> DashboardSummaryResponse:
    """Build dashboard summary for the authenticated user.

    Combines ledger balances with purchase portfolio aggregates.
    All amounts in USD cents.
    """
    # -- 1. Ledger balances (reuse existing service functions) --
    active_bal = await get_active_balance(session, user_id)
    passive_bal = await get_passive_balance(session, user_id)

    # -- 2. Purchase aggregates grouped by company --
    stmt = (
        select(
            Purchase.company_id,
            CompanyProfile.name.label("company_name"),
            CompanyProfile.logo_url.label("logo_url"),
            CompanyProfile.price_per_unit_cents.label("current_price"),
            func.coalesce(func.sum(Purchase.units), 0).label("total_units"),
            func.coalesce(func.sum(Purchase.paid_cents), 0).label("invested_cents"),
        )
        .join(CompanyProfile, Purchase.company_id == CompanyProfile.id)
        .where(
            Purchase.investor_id == user_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
        .group_by(
            Purchase.company_id,
            CompanyProfile.name,
            CompanyProfile.logo_url,
            CompanyProfile.price_per_unit_cents,
        )
        .order_by(func.sum(Purchase.units).desc())
    )

    result = await session.execute(stmt)
    rows = result.all()

    # -- 3. Build per-company summaries and totals --
    companies: list[CompanySummaryResponse] = []
    total_units = 0
    total_invested = 0
    total_current_value = 0

    for row in rows:
        units = int(row.total_units)
        invested = int(row.invested_cents)
        current_value = units * int(row.current_price)

        companies.append(CompanySummaryResponse(
            company_id=row.company_id,
            company_name=row.company_name,
            logo_url=row.logo_url,
            total_units=units,
            invested_cents=invested,
            current_value_cents=current_value,
        ))

        total_units += units
        total_invested += invested
        total_current_value += current_value

    return DashboardSummaryResponse(
        active_balance=BalanceResponse(**active_bal),
        passive_balance=BalanceResponse(**passive_bal),
        total_invested_cents=total_invested,
        total_units=total_units,
        current_value_cents=total_current_value,
        companies_count=len(companies),
        companies=companies,
    )
