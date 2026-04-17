# =============================================================================
# CBSHOME Backend -- Product Public Router (Sprint 4.2 + Sprint 6.1 + F4.1
#                                            + F4.1.1 hotfix)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/products       -- list active products (public)
#   GET /api/v1/products/{id}  -- product detail with installments (public)
#
# AUTH:
#   No authentication required. Public storefront.
#
# Sprint 6.1 CHANGES:
#   - sold_units populated from real Purchase count (TD-031)
#
# Phase 4 FIX:
#   Detail endpoint returns 404 for non-active products.
#   Previously returned hidden/archived products by UUID,
#   leaking sold_units data for unpublished products.
#
# Sprint F4.1 CHANGES:
#   - List endpoint batch-loads CompanyProfile rows for all products on
#     the current page and denormalises company_name / company_logo_url
#     / company_cover_url into the response. One extra SELECT per page
#     (not per product) -- no N+1.
#   - Detail endpoint loads the owning company via a direct SELECT and
#     denormalises the same three fields.
#
# F4.1.1 hotfix:
#   - Missing company for an existing product (violates FK RESTRICT) now
#     raises an explicit RuntimeError naming product_id AND company_id,
#     yielding a 500 with a grep-able trace instead of a bare KeyError
#     (list) or a misleading 404 NotFoundError (detail, via get_company).
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
from app.modules.companies.models import CompanyProfile
from app.modules.products.constants import ProductStatus
from app.modules.products.schemas import (
    InstallmentResponse,
    PublicProductDetailResponse,
    PublicProductListResponse,
    PublicProductResponse,
)
from app.modules.products.service import get_product_detail, list_products
from app.modules.purchases.service import get_sold_units_map

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.get(
    "",
    response_model=PublicProductListResponse,
)
async def list_products_endpoint(
    company_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_reader),
) -> PublicProductListResponse:
    """List active products (public storefront)."""
    products, total = await list_products(
        session,
        active_only=True,
        company_id=company_id,
        page=page,
        per_page=per_page,
    )

    # Fetch sold_units for all products in one query.
    product_ids = [p.id for p in products]
    sold_map = await get_sold_units_map(session, product_ids)

    # Batch-load companies for denormalisation (Sprint F4.1).
    # One SELECT per page, not per product.
    company_ids = list({p.company_id for p in products})
    if company_ids:
        companies_stmt = select(CompanyProfile).where(
            CompanyProfile.id.in_(company_ids)
        )
        companies_result = await session.execute(companies_stmt)
        companies_map = {c.id: c for c in companies_result.scalars().all()}
    else:
        companies_map = {}

    items = []
    for p in products:
        resp = PublicProductResponse.model_validate(p)
        resp.sold_units = sold_map.get(p.id, 0)
        # FK is RESTRICT -- missing company is a data integrity bug.
        # Surface it explicitly (500 with a grep-able message) rather
        # than a bare KeyError (F4.1.1 hotfix).
        company = companies_map.get(p.company_id)
        if company is None:
            raise RuntimeError(
                f"Data integrity: product {p.id} references "
                f"missing company {p.company_id}"
            )
        resp.company_name = company.name
        resp.company_logo_url = company.logo_url
        resp.company_cover_url = company.cover_url
        items.append(resp)

    return PublicProductListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{product_id}",
    response_model=PublicProductDetailResponse,
)
async def get_product_detail_endpoint(
    product_id: UUID,
    session: AsyncSession = Depends(get_db_reader),
) -> PublicProductDetailResponse:
    """Get product detail with installment plans (public).

    Returns 404 for non-active products (hidden/archived).
    """
    product, installments = await get_product_detail(product_id, session)

    # Public endpoint: only active products are visible.
    if product.status != ProductStatus.ACTIVE:
        raise NotFoundError("Product not found")

    sold_map = await get_sold_units_map(session, [product.id])

    # Load the owning company directly. We intentionally do NOT call
    # get_company() here because its NotFoundError -> 404 would mislead
    # the investor into thinking the product does not exist, when
    # actually the product is fine and the FK-backed company row is
    # missing -- a server-side data integrity bug (F4.1.1 hotfix).
    company_stmt = select(CompanyProfile).where(
        CompanyProfile.id == product.company_id
    )
    company = (await session.execute(company_stmt)).scalar_one_or_none()
    if company is None:
        raise RuntimeError(
            f"Data integrity: product {product.id} references "
            f"missing company {product.company_id}"
        )

    response = PublicProductDetailResponse.model_validate(product)
    response.sold_units = sold_map.get(product.id, 0)
    response.company_name = company.name
    response.company_logo_url = company.logo_url
    response.company_cover_url = company.cover_url
    response.installments = [
        InstallmentResponse.model_validate(inst) for inst in installments
    ]
    return response
