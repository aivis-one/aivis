# =============================================================================
# CBSHOME Backend -- Portfolio Service (Sprint 9.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   get_portfolio()          -- all company positions for investor
#   get_company_position()   -- single company position + paginated purchases
#
# AVERAGE PRICE:
#   avg_price_cents = SUM(paid_cents) / SUM(units WHERE legal_basis='sale')
#   Gift purchases (paid_cents=0, legal_basis=gift) are excluded from avg.
#   If sale_units == 0, avg_price_cents = 0.
#
# COMMIT RULE (P-01):
#   Service never commits. Read-only queries via get_db_reader.
# =============================================================================

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.portfolio.schemas import (
    CompanyPositionDetailResponse,
    CompanyPositionResponse,
    PortfolioResponse,
    PurchaseItemResponse,
)
from app.modules.purchases.constants import PurchaseLegalBasis, PurchaseStatus
from app.modules.purchases.models import Purchase


def _compute_avg_price(total_paid_cents: int, sale_units: int) -> int:
    """Compute average purchase price per unit (sale purchases only).

    Returns 0 if investor has no sale units for a company.
    """
    if sale_units <= 0:
        return 0
    return total_paid_cents // sale_units


async def get_portfolio(
    user_id: UUID,
    session: AsyncSession,
) -> PortfolioResponse:
    """Get full portfolio: positions grouped by company.

    Returns all companies where the user has active purchases,
    sorted by current_value descending.
    """
    stmt = (
        select(
            Purchase.company_id,
            CompanyProfile.name.label("company_name"),
            CompanyProfile.logo_url.label("logo_url"),
            CompanyProfile.price_per_unit_cents.label("current_price"),
            func.coalesce(func.sum(Purchase.units), 0).label("total_units"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Purchase.legal_basis == PurchaseLegalBasis.SALE,
                            Purchase.units,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("sale_units"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Purchase.legal_basis != PurchaseLegalBasis.SALE,
                            Purchase.units,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("gift_units"),
            func.coalesce(func.sum(Purchase.paid_cents), 0).label("total_paid"),
            func.count().label("purchases_count"),
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
        .order_by(
            (func.sum(Purchase.units) * CompanyProfile.price_per_unit_cents).desc()
        )
    )

    result = await session.execute(stmt)
    rows = result.all()

    positions: list[CompanyPositionResponse] = []

    for row in rows:
        total_units = int(row.total_units)
        sale_units = int(row.sale_units)
        gift_units = int(row.gift_units)
        total_paid = int(row.total_paid)
        current_price = int(row.current_price)

        positions.append(CompanyPositionResponse(
            company_id=row.company_id,
            company_name=row.company_name,
            logo_url=row.logo_url,
            total_units=total_units,
            sale_units=sale_units,
            gift_units=gift_units,
            total_paid_cents=total_paid,
            avg_price_cents=_compute_avg_price(total_paid, sale_units),
            current_price_cents=current_price,
            current_value_cents=total_units * current_price,
            purchases_count=int(row.purchases_count),
        ))

    return PortfolioResponse(positions=positions)


async def get_company_position(
    user_id: UUID,
    company_id: UUID,
    session: AsyncSession,
    *,
    page: int = 1,
    per_page: int = 20,
) -> CompanyPositionDetailResponse:
    """Get position detail for a single company with paginated purchases.

    Raises:
        NotFoundError: If investor has no active purchases in this company.
    """
    # -- 1. Aggregate position --
    agg_stmt = (
        select(
            CompanyProfile.name.label("company_name"),
            CompanyProfile.logo_url.label("logo_url"),
            CompanyProfile.price_per_unit_cents.label("current_price"),
            func.coalesce(func.sum(Purchase.units), 0).label("total_units"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Purchase.legal_basis == PurchaseLegalBasis.SALE,
                            Purchase.units,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("sale_units"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Purchase.legal_basis != PurchaseLegalBasis.SALE,
                            Purchase.units,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("gift_units"),
            func.coalesce(func.sum(Purchase.paid_cents), 0).label("total_paid"),
        )
        .join(CompanyProfile, Purchase.company_id == CompanyProfile.id)
        .where(
            Purchase.investor_id == user_id,
            Purchase.company_id == company_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
        .group_by(
            CompanyProfile.name,
            CompanyProfile.logo_url,
            CompanyProfile.price_per_unit_cents,
        )
    )

    agg_result = await session.execute(agg_stmt)
    agg_row = agg_result.one_or_none()

    if agg_row is None:
        raise NotFoundError("No portfolio position in this company")

    total_units = int(agg_row.total_units)
    sale_units = int(agg_row.sale_units)
    gift_units = int(agg_row.gift_units)
    total_paid = int(agg_row.total_paid)
    current_price = int(agg_row.current_price)

    # -- 2. Count total purchases for pagination --
    count_stmt = (
        select(func.count())
        .select_from(Purchase)
        .where(
            Purchase.investor_id == user_id,
            Purchase.company_id == company_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
    )
    total_count = (await session.execute(count_stmt)).scalar_one()

    # -- 3. Paginated purchases --
    offset = (page - 1) * per_page
    purchases_stmt = (
        select(Purchase)
        .where(
            Purchase.investor_id == user_id,
            Purchase.company_id == company_id,
            Purchase.status == PurchaseStatus.ACTIVE,
        )
        .order_by(Purchase.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )

    purchases_result = await session.execute(purchases_stmt)
    purchases = list(purchases_result.scalars().all())

    return CompanyPositionDetailResponse(
        company_id=company_id,
        company_name=agg_row.company_name,
        logo_url=agg_row.logo_url,
        total_units=total_units,
        sale_units=sale_units,
        gift_units=gift_units,
        total_paid_cents=total_paid,
        avg_price_cents=_compute_avg_price(total_paid, sale_units),
        current_price_cents=current_price,
        current_value_cents=total_units * current_price,
        purchases=[PurchaseItemResponse.model_validate(p) for p in purchases],
        total=total_count,
        page=page,
        per_page=per_page,
    )
