# =============================================================================
# AIVIS.ONE Backend -- Product Public Router (iter 2.4 R1 §1.6.2 + §1.6.3)
# =============================================================================
#
# ENDPOINTS (no authentication):
#   GET /api/v1/public/products            -- paginated list of active products
#                                             (?company_id=, ?page=, ?per_page=)
#   GET /api/v1/public/products/{id}       -- product detail with installment
#                                             plans
#
# iter 2.4 MIGRATION (products → /api/v1/public/*):
#   The list / detail surface lived at /api/v1/products before this
#   iteration. Moved here to match the companies/attachments public-flow
#   shape -- one prefix for the entire storefront browsing surface, one
#   rate-limit bucket, one WAF policy. Identical request/response shape
#   so the frontend only swaps the URL prefix.
#
#   products/router.py is REMOVED in the same change set; main.py no
#   longer imports or registers it. Staff-flow stays at
#   /api/v1/staff/products via products/staff_router.py.
#
# R1 §1.6.3 INSTALLMENTS STRIP:
#   The public product detail response carries installment plans, but
#   `plan_config.agent_bonus_units` (per-tranche agent commission units)
#   must not leak through the public surface -- it is operational data
#   for Staff and the company itself. The strip happens here, in the
#   router, by rebuilding each InstallmentResponse with a cleaned
#   plan_config. Staff endpoints keep the full plan_config.
#
# RATE LIMITING (R1 §1.6.4):
#   Shares the `public_companies:` Redis bucket prefix with
#   companies/public_router. PUBLIC_COMPANIES_RATE_LIMIT (60/60s) per
#   IP covers the combined companies+products browsing budget so a
#   client clicking list → company detail → product detail stays in
#   one window rather than three.
#
# Sprint 4.4 PATTERNS PRESERVED:
#   - Explicit-constructor response building (no ORM mutation, no
#     post-validate assignment). See products/router.py history for
#     rationale.
#   - F4.1.1 hotfix: missing CompanyProfile FK -> RuntimeError 500
#     with a grep-able message, not a misleading 404.
#
# COMMIT RULE (P-01):
#   Read-only endpoints, get_db_reader. No commits.
# =============================================================================

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import get_client_ip
from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
from app.core.rate_limit import check_rate_limit
from app.modules.companies.constants import PUBLIC_COMPANIES_RATE_LIMIT
from app.modules.companies.models import CompanyProfile
from app.modules.products.constants import ProductStatus
from app.modules.products.schemas import (
    InstallmentResponse,
    PublicProductDetailResponse,
    PublicProductListResponse,
    PublicProductResponse,
)
from app.modules.products.service import get_product_detail, list_products
from app.modules.purchases.service import get_available_packages_map

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/public/products",
    tags=["public-products"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _public_products_rate_limit(request: Request) -> None:
    """Apply the shared `public_companies:` bucket per request.

    Same prefix as companies/public_router. PUBLIC_COMPANIES_RATE_LIMIT
    is the canonical limit for the public storefront-browse experience
    regardless of which resource (company or product) is being fetched.
    """
    ip = get_client_ip(request)
    max_req, window = PUBLIC_COMPANIES_RATE_LIMIT
    await check_rate_limit(
        f"public_companies:{ip}",
        max_requests=max_req,
        window_seconds=window,
        error_message="Too many requests. Please try again later.",
    )


def _strip_agent_bonus_units(plan_config: dict[str, Any]) -> dict[str, Any]:
    """Return a plan_config copy with `agent_bonus_units` removed.

    R1 §1.6.3: per-tranche agent commission units must not leak via
    the public product detail. The key sits at the top level of
    plan_config (see products/constants.py::validate_plan_config and
    calculator.py for the canonical shape); a shallow dict-comp is
    sufficient. Staff and company endpoints keep the full plan_config.
    """
    return {k: v for k, v in plan_config.items() if k != "agent_bonus_units"}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PublicProductListResponse,
)
async def list_public_products_endpoint(
    request: Request,
    company_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_reader),
) -> PublicProductListResponse:
    """List active products (public storefront).

    Optional ?company_id filters to a single company. Response items
    carry denormalised company_name / logo / cover via a batch lookup
    so the grid renders without a second round-trip.
    """
    await _public_products_rate_limit(request)

    products, total = await list_products(
        session,
        active_only=True,
        company_id=company_id,
        page=page,
        per_page=per_page,
    )

    # Sprint 4.3: compute available packages per product from the active
    # pool of each product's company. One pool-per-company SELECT inside
    # the helper, not per product.
    product_ids = [p.id for p in products]
    company_ids = list({p.company_id for p in products})
    available_map = await get_available_packages_map(
        session, company_ids=company_ids, product_ids=product_ids
    )

    # Batch-load companies for denormalisation (Sprint F4.1). One
    # SELECT per page, not per product.
    if company_ids:
        companies_stmt = select(CompanyProfile).where(
            CompanyProfile.id.in_(company_ids)
        )
        companies_result = await session.execute(companies_stmt)
        companies_map: dict[UUID, CompanyProfile] = {
            c.id: c for c in companies_result.scalars().all()
        }
    else:
        companies_map = {}

    items: list[PublicProductResponse] = []
    for p in products:
        # FK is RESTRICT -- missing company is a data integrity bug.
        # Surface it explicitly (500 with a grep-able message) rather
        # than a bare KeyError (F4.1.1 hotfix carried over).
        company = companies_map.get(p.company_id)
        if company is None:
            raise RuntimeError(
                f"Data integrity: product {p.id} references "
                f"missing company {p.company_id}"
            )

        # Sprint 4.4 explicit-constructor pattern. Every field passed
        # by keyword; missing field is a loud TypeError at server start
        # rather than a silent default.
        items.append(
            PublicProductResponse(
                id=p.id,
                company_id=p.company_id,
                name=p.name,
                description=p.description,
                package_size=p.package_size,
                price_per_unit_cents=p.price_per_unit_cents,
                price_per_pack_cents=p.package_size * p.price_per_unit_cents,
                cover_url=p.cover_url,
                available_packages=available_map.get(p.id, 0),
                company_name=company.name,
                company_logo_url=company.logo_url,
                company_cover_url=company.cover_url,
            )
        )

    return PublicProductListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get(
    "/{product_id}",
    response_model=PublicProductDetailResponse,
)
async def get_public_product_detail_endpoint(
    product_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> PublicProductDetailResponse:
    """Get product detail with installment plans (public).

    Returns 404 for non-active products (hidden / archived).

    R1 §1.6.3: per-tranche agent commission units are stripped from
    every installment's plan_config before serialisation.
    """
    await _public_products_rate_limit(request)

    product, installments = await get_product_detail(product_id, session)

    if product.status != ProductStatus.ACTIVE:
        raise NotFoundError("Product not found")

    available_map = await get_available_packages_map(
        session,
        company_ids=[product.company_id],
        product_ids=[product.id],
    )

    # Load owning company directly. We do not call get_company() here
    # because its NotFoundError -> 404 would mislead the investor into
    # thinking the product is missing, when actually it's a server-
    # side data-integrity bug (F4.1.1 hotfix).
    company_stmt = select(CompanyProfile).where(
        CompanyProfile.id == product.company_id
    )
    company = (await session.execute(company_stmt)).scalar_one_or_none()
    if company is None:
        raise RuntimeError(
            f"Data integrity: product {product.id} references "
            f"missing company {product.company_id}"
        )

    # R1 §1.6.3: build each installment with a stripped plan_config.
    # Rebuild via the schema constructor rather than mutating the ORM
    # instance -- same pattern as Sprint 4.4 explicit response building.
    public_installments = [
        InstallmentResponse(
            id=inst.id,
            product_id=inst.product_id,
            name=inst.name,
            plan_config=_strip_agent_bonus_units(inst.plan_config),
            created_at=inst.created_at,
        )
        for inst in installments
    ]

    return PublicProductDetailResponse(
        id=product.id,
        company_id=product.company_id,
        name=product.name,
        description=product.description,
        package_size=product.package_size,
        price_per_unit_cents=product.price_per_unit_cents,
        price_per_pack_cents=product.package_size * product.price_per_unit_cents,
        cover_url=product.cover_url,
        available_packages=available_map.get(product.id, 0),
        company_name=company.name,
        company_logo_url=company.logo_url,
        company_cover_url=company.cover_url,
        installments=public_installments,
    )
