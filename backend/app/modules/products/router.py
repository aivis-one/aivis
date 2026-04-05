# =============================================================================
# CBSHOME Backend -- Product Public Router (Sprint 4.2)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/products       -- list active products (public)
#   GET /api/v1/products/{id}  -- product detail with installments (public)
#
# AUTH:
#   No authentication required. Public storefront.
# =============================================================================

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.modules.products.schemas import (
    InstallmentResponse,
    PublicProductDetailResponse,
    PublicProductListResponse,
    PublicProductResponse,
)
from app.modules.products.service import get_product_detail, list_products

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
    return PublicProductListResponse(
        items=[PublicProductResponse.model_validate(p) for p in products],
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
    """Get product detail with installment plans (public)."""
    product, installments = await get_product_detail(product_id, session)
    response = PublicProductDetailResponse.model_validate(product)
    response.installments = [
        InstallmentResponse.model_validate(inst) for inst in installments
    ]
    return response
