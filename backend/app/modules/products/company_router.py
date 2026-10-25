# =============================================================================
# AIVIS.ONE Backend -- Product Company Router
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/company/products -- the caller's own products, every status
#
# AUTH:
#   Requires role=company: get_current_company_profile resolves the caller's
#   own CompanyProfile and raises 403 for anyone else. There is no company_id
#   parameter, so a company can only ever address its own products.
#
# WHY IT EXISTS:
#   The only non-staff product list is public and active-only
#   (products/public_router.py). The owner sees ALL of his products,
#   hidden and archived included; this route is that view and
#   reuses list_products(active_only=False, company_id=...).
#
# COMMIT RULE (P-01):
#   Read-only, uses get_db_reader.
# =============================================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.i18n import reader_language
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.companies.media import build_product_response
from app.modules.products.schemas import ProductListResponse
from app.modules.products.service import list_products

router = APIRouter(prefix="/api/v1/company/products", tags=["company-products"])


@router.get("", response_model=ProductListResponse)
async def list_my_products(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_reader),
    reader: str = Depends(reader_language),
) -> ProductListResponse:
    """List the authenticated company's own products, including hidden
    and archived ones."""
    products, total = await list_products(
        session,
        active_only=False,
        company_id=company.id,
        page=page,
        per_page=per_page,
    )
    return ProductListResponse(
        items=[await build_product_response(p, reader) for p in products],
        total=total,
        page=page,
        per_page=per_page,
    )
