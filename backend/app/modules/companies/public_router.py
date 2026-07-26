# =============================================================================
# AIVIS.ONE Backend -- Company Public Router (iter 2.4 R1 §1.6.2)
# =============================================================================
#
# ENDPOINTS (no authentication):
#   GET /api/v1/public/companies         -- paginated list of active companies
#                                           (?search=, ?page=, ?per_page=)
#   GET /api/v1/public/companies/{id}    -- company detail with stats + roadmap
#
# iter 2.4 MIGRATION (companies → /api/v1/public/*):
#   The list / detail surface lived at /api/v1/companies before this
#   iteration. Attachments under iter 2.2 already used the
#   /api/v1/public/companies/{id}/attachments shape; companies and
#   products now follow the same convention so:
#     - operations / WAF / Sentry sampling can target a single prefix
#       (R1 §1.6.4 envisages 60 req/min/IP under one bucket);
#     - useAuthWall + PublicShell on the frontend detect public surface
#       from the URL without an endpoint allow-list;
#     - the `/me` auth-flow stays at /api/v1/companies/me where the
#       company-role caller already expects it (not migrated).
#
#   GET /api/v1/companies/me is intentionally left in companies/router.py
#   because it is auth-only and tied to a different audience.
#
# STATS (R1 §1.6.2):
#   detail surface always carries `stats: PublicCompanyStatsResponse`
#   (pool_total_options / options_sold / options_sold_percent /
#   price_growth_90d_percent). Filled by service.get_public_company_stats
#   in the same request as get_company_detail; no extra round-trip
#   from the frontend.
#
# ROADMAP (R1 §5):
#   roadmap items carry kind / valid_until / external_url / cover_url
#   (presigned) / linked_product_id / embedded post snippet.
#   get_company_detail batch-loads referenced posts to avoid N+1.
#
# RATE LIMITING (R1 §1.6.4):
#   PUBLIC_COMPANIES_RATE_LIMIT (60 / 60s) per IP. The Redis key prefix
#   `public_companies:` is intentionally generic so products' public
#   router (C3, same iteration) can share the same bucket -- one budget
#   for the entire storefront-browse experience per IP.
#
# COMMIT RULE (P-01):
#   Read-only endpoints, get_db_reader. No commits.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
from app.core.rate_limit import check_rate_limit
from app.modules.companies.constants import (
    PUBLIC_COMPANIES_RATE_LIMIT,
    CompanyStatus,
)
from app.modules.companies.schemas import (
    PublicCompanyDetailResponse,
    PublicCompanyListResponse,
    PublicCompanyResponse,
)
from app.modules.companies.service import (
    build_roadmap_item_response,
    get_company_detail,
    get_public_company_stats,
    list_companies,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/public/companies",
    tags=["public-companies"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Real-IP (set by Nginx); fall back to
    request.client.host for dev/test. Mirrors the same helper in
    auth/router and attachments_public_router so the rate-limit key
    shape stays consistent across the codebase.
    """
    return (
        request.headers.get("X-Real-IP")
        or (request.client.host if request.client else "unknown")
    )


async def _public_companies_rate_limit(request: Request) -> None:
    """Apply the shared `public_companies:` bucket per request.

    Pulled out into a helper because the two endpoints below would
    otherwise repeat the same five lines verbatim. The same prefix is
    reused by products/public_router (C3) so an IP that browses
    list + detail + product detail under the storefront stays within
    one 60-per-minute budget rather than three independent ones.
    """
    ip = _get_client_ip(request)
    max_req, window = PUBLIC_COMPANIES_RATE_LIMIT
    await check_rate_limit(
        f"public_companies:{ip}",
        max_requests=max_req,
        window_seconds=window,
        error_message="Too many requests. Please try again later.",
    )


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PublicCompanyListResponse,
)
async def list_public_companies_endpoint(
    request: Request,
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_reader),
) -> PublicCompanyListResponse:
    """List active companies (public storefront).

    Optional ?search=<str> does a case-insensitive substring match on
    company name; service layer escapes %/_/\\ so the user can type
    literal metacharacters.
    """
    await _public_companies_rate_limit(request)

    companies, total = await list_companies(
        session,
        active_only=True,
        search=search,
        page=page,
        per_page=per_page,
    )
    return PublicCompanyListResponse(
        items=[PublicCompanyResponse.model_validate(c) for c in companies],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# Detail (stats + roadmap inline)
# ---------------------------------------------------------------------------


@router.get(
    "/{company_id}",
    response_model=PublicCompanyDetailResponse,
)
async def get_public_company_detail_endpoint(
    company_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> PublicCompanyDetailResponse:
    """Get company detail with storefront stats and roadmap items.

    Returns 404 for non-active companies (hidden / archived). Roadmap
    items follow R1 §5 (kind, cover_url presigned, post snippet,
    linked product); stats follows R1 §1.6.2 (pool / growth aggregates).
    """
    await _public_companies_rate_limit(request)

    profile, roadmap_items, posts_map = await get_company_detail(
        company_id, session
    )

    if profile.status != CompanyStatus.ACTIVE:
        raise NotFoundError("Company not found")

    stats = await get_public_company_stats(company_id, session)

    roadmap = [
        await build_roadmap_item_response(
            item,
            posts_map.get(item.post_id) if item.post_id else None,
            session,
        )
        for item in roadmap_items
    ]
    return PublicCompanyDetailResponse(
        **PublicCompanyResponse.model_validate(profile).model_dump(),
        stats=stats,
        roadmap=roadmap,
    )
