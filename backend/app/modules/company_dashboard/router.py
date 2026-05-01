# =============================================================================
# CBSHOME Backend -- Company Dashboard Router (Sprint 4.3 / B5)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/company/dashboard   -- aggregated dashboard with
#                                      embedded pool snapshot
#   GET /api/v1/company/analytics   -- sales analytics (lifetime +
#                                      this month + by-month +
#                                      by-product breakdowns)
#
# AUTH:
#   Both endpoints rely on get_current_company_profile() (in
#   companies/dependencies.py), which authenticates the caller and
#   loads their CompanyProfile. A user without a CompanyProfile gets
#   a 403 "User is not linked to a company" -- this covers
#   investors/agents/staff calling /company/* by mistake.
#
# COMMIT RULE (P-01):
#   Read-only endpoints use get_db_reader.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.company_dashboard.schemas import (
    CompanyAnalyticsResponse,
    CompanyDashboardResponse,
)
from app.modules.company_dashboard.service import (
    get_company_analytics,
    get_company_dashboard,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/company", tags=["company-dashboard"])


@router.get(
    "/dashboard",
    response_model=CompanyDashboardResponse,
)
async def get_company_dashboard_endpoint(
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanyDashboardResponse:
    """Aggregated dashboard for the authenticated company.

    Returns: passive balance, lifetime revenue, total sale options,
    products count, embedded pool snapshot (or null), last 20
    transactions.
    """
    return await get_company_dashboard(company, session)


@router.get(
    "/analytics",
    response_model=CompanyAnalyticsResponse,
)
async def get_company_analytics_endpoint(
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanyAnalyticsResponse:
    """Sales analytics for the authenticated company.

    Returns: lifetime revenue + sale options, revenue this month,
    sales_by_month (last 12 months that had sales, oldest first),
    sales_by_product (ALL products of the company including archived
    and zero-sales, sorted by revenue DESC).
    """
    return await get_company_analytics(company, session)
