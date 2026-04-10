# =============================================================================
# CBSHOME Backend -- Product Public Router (Sprint 4.2 + Sprint 6.1, fix Phase 4)
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
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
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

    items = []
    for p in products:
        resp = PublicProductResponse.model_validate(p)
        resp.sold_units = sold_map.get(p.id, 0)
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

    response = PublicProductDetailResponse.model_validate(product)
    response.sold_units = sold_map.get(product.id, 0)
    response.installments = [
        InstallmentResponse.model_validate(inst) for inst in installments
    ]
    return response
