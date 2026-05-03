# =============================================================================
# CBSHOME Backend -- Product Public Router (Sprint 4.2 + Sprint 6.1 + F4.1
#                                            + F4.1.1 hotfix + Sprint 4.3
#                                            + Sprint 4.4)
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
#
# Sprint 4.3 CHANGES (TD-071 / Share Pool Refactor):
#   - sold_units (COUNT of purchases) replaced with available_packages
#     (floor(pool_remaining / package_size)). Sourced from the new
#     get_available_packages_map() in purchases/service.py, which keys
#     by product_id and consults the active OptionPool of each product's
#     company. The company-level batch SELECT was already happening for
#     denormalisation -- we now also pass company_ids through to the
#     packages map.
#
# Sprint 4.4 CHANGES (B7 UX hardening + post-review hardening):
#   - Both endpoints populate the new price_per_pack_cents field on the
#     response right next to available_packages. Pure int arithmetic
#     (package_size * price_per_unit_cents) -- no extra SELECTs, no
#     Decimal/float drift.
#   - Sprint 4.4 dropped the `= 0` default on available_packages, the
#     `= ""` default on company_name, and the `= []` default on
#     installments.
#
#   - PRE-REVIEW PATTERN (rejected by code review):
#       p.available_packages = available_map.get(p.id, 0)  # mutate ORM
#       resp = PublicProductResponse.model_validate(p)     # validate
#       resp.company_name = company.name                   # mutate response
#     Two issues. (1) Mutating an ORM-loaded row reaches into SQLAlchemy
#     session bookkeeping; safe today on read-only sessions, brittle if
#     the session ever switches to write mode. (2) Mutating the response
#     object after model_validate sidesteps Pydantic validation for the
#     fields that get assigned post-hoc -- they happen to be plain
#     str/int, but the pattern erodes the schema's authority.
#
#   - POST-REVIEW PATTERN (this file):
#       PublicProductResponse(
#           id=..., name=..., available_packages=..., company_name=...,
#       )
#     Every field passed by keyword to the constructor. No ORM mutation,
#     no post-validate assignment. Trade-off: a new schema field must be
#     added at every constructor call site or the build fails at
#     server-start with a clear TypeError. That tradeoff is intentional --
#     a missing field on the response is a contract bug we want loud,
#     not a soft `model_validate(p)` slipping through with a default.
#
#   - The detail endpoint passes installments=[...] explicitly even
#     when the list is empty. The schema now requires the field; the
#     router must always populate it. No `?? []` compensation needed
#     on the frontend.
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
from app.modules.purchases.service import get_available_packages_map

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

    # Sprint 4.3: compute available packages per product from the active
    # pool of each product's company. One pool-per-company SELECT inside
    # the helper, not per product.
    product_ids = [p.id for p in products]
    company_ids = list({p.company_id for p in products})
    available_map = await get_available_packages_map(
        session, company_ids=company_ids, product_ids=product_ids
    )

    # Batch-load companies for denormalisation (Sprint F4.1).
    # One SELECT per page, not per product.
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
        # than a bare KeyError (F4.1.1 hotfix).
        company = companies_map.get(p.company_id)
        if company is None:
            raise RuntimeError(
                f"Data integrity: product {p.id} references "
                f"missing company {p.company_id}"
            )

        # Sprint 4.4: explicit constructor. Every field passed by
        # keyword. No ORM mutation, no post-validate assignment.
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

    # Sprint 4.3: single-product variant of the same packages helper.
    available_map = await get_available_packages_map(
        session,
        company_ids=[product.company_id],
        product_ids=[product.id],
    )

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

    # Sprint 4.4: explicit constructor. installments is passed
    # explicitly even when empty -- the schema requires it (no `= []`
    # default on the response model), so the frontend can drop its
    # `?? []` compensation in three places.
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
        installments=[
            InstallmentResponse.model_validate(inst) for inst in installments
        ],
    )
