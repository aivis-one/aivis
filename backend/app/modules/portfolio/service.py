# =============================================================================
# CBSHOME Backend -- Portfolio Service (Sprint 9.2 + Sprint 4.6 hotfix)
# =============================================================================
#
# RESPONSIBILITIES:
#   get_portfolio()          -- all company positions for investor
#   get_company_position()   -- single company position + paginated purchases
#
# AVERAGE PRICE:
#   avg_price_cents = SUM(paid_cents) / SUM(units WHERE legal_basis IN
#                                            ('sale', 'installment_tranche'))
#   Gift purchases (legal_basis='gift', paid_cents=0) are excluded from
#   the average. If the resulting "paid_units" denominator is zero
#   (gift-only portfolio for this company), avg_price_cents = 0.
#
# Sprint 4.6 hotfix:
#   Pre-fix the aggregation classified `installment_tranche` purchases
#   as gifts (because the case-when used `legal_basis != SALE` for
#   gifts). An investor who paid a tranche then saw their portfolio
#   row as `sale_units=0, gift_units=N, avg_price=$0.00, invested=$X` --
#   contradictory: invested > 0 but every unit was "gifted". Reported
#   from production: investor cd5db920... viewing Immo-Pro-Invest GmbH
#   showed total_units=1250, gift_units=1250, sale_units=0,
#   total_paid_cents=118750, avg_price=0.
#
#   Fix: classify by explicit enum membership. installment_tranche
#   purchases are commercial sales-in-instalments, so they roll up
#   into the same bucket as instant SALE purchases for the purpose
#   of avg_price and the "purchased vs gifted" split shown in the UI.
#   GIFT is the only basis that contributes to gift_units.
#
#   Schema fields are unchanged (sale_units / gift_units), so the
#   frontend type contract holds. Only the math behind them changes.
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


# Legal-basis values that count as a paid acquisition for the purpose
# of avg-price math and the "purchased" UI label. Instant SALE and
# INSTALLMENT_TRANCHE are both money-moving events from the investor;
# GIFT is free shares and lives in its own bucket.
_PAID_LEGAL_BASES = (
    PurchaseLegalBasis.SALE,
    PurchaseLegalBasis.INSTALLMENT_TRANCHE,
)


def _compute_avg_price(total_paid_cents: int, paid_units: int) -> int:
    """Compute average purchase price per unit (paid acquisitions only).

    `paid_units` is the sum of units across legal_basis IN
    ('sale', 'installment_tranche') -- i.e. units the investor paid
    money for, regardless of whether the payment was instant or
    spread across tranches. Gifts are excluded.

    Returns 0 when the denominator is non-positive (gift-only
    portfolio for the company in question).
    """
    if paid_units <= 0:
        return 0
    return round(total_paid_cents / paid_units)


# Reusable case-when fragments. Defined as helpers so the two
# aggregation queries below share one source of truth -- if we ever
# need to add another paid basis (e.g. a future "barter" type), one
# edit instead of two.
def _sale_units_expr() -> object:
    """SUM(units) for paid acquisitions (sale + installment_tranche)."""
    return func.coalesce(
        func.sum(
            case(
                (
                    Purchase.legal_basis.in_(_PAID_LEGAL_BASES),
                    Purchase.units,
                ),
                else_=0,
            )
        ),
        0,
    )


def _gift_units_expr() -> object:
    """SUM(units) for legal_basis='gift'.

    Sprint 4.6 hotfix: was `legal_basis != SALE`, which silently
    captured installment_tranche as gift. Now matches GIFT explicitly.
    """
    return func.coalesce(
        func.sum(
            case(
                (
                    Purchase.legal_basis == PurchaseLegalBasis.GIFT,
                    Purchase.units,
                ),
                else_=0,
            )
        ),
        0,
    )


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
            _sale_units_expr().label("sale_units"),
            _gift_units_expr().label("gift_units"),
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
            _sale_units_expr().label("sale_units"),
            _gift_units_expr().label("gift_units"),
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
