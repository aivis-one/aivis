# =============================================================================
# CBSHOME Backend -- Company Staff Router (Sprint 4.1, fix Phase 4,
#                                            iter 2.6c B2)
# =============================================================================
#
# ENDPOINTS:
#   GET   /api/v1/staff/companies                          -- list (paginated)
#   POST  /api/v1/staff/companies                          -- create company
#   PATCH /api/v1/staff/companies/{id}                     -- update profile
#   PATCH /api/v1/staff/companies/{id}/price               -- change price
#   POST  /api/v1/staff/companies/{id}/roadmap             -- add roadmap item
#   PATCH /api/v1/staff/companies/{id}/roadmap/{item_id}   -- update roadmap item
#   DELETE /api/v1/staff/companies/{id}/roadmap/{item_id}  -- soft-delete item
#   PATCH /api/v1/staff/companies/{id}/roadmap/reorder     -- reorder items
#
# PERMISSIONS:
#   All endpoints require company_manage permission.
#   Create, price change, and distribution_config update also require
#   financial_operations permission.
#
# Phase 4 FIX:
#   _require_permission / _require_financial_operations extracted to
#   staff/permissions.py (was duplicated in products/staff_router.py).
#
# iter 2.6c B2:
#   GET /staff/companies surfaces every company (active / hidden /
#   archived) with optional ?status= (typed CompanyStatus, 422 on
#   garbage values) and ?search= (case-insensitive ilike on name,
#   metacharacters escaped server-side). Pagination is consistent with
#   the rest of the staff list endpoints (page / per_page).
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session, get_db_reader
from app.core.exceptions import BadRequestError
from app.modules.auth.dependencies import (
    get_current_user_write,
    require_staff_permission,
)
from app.modules.companies.constants import (
    ROADMAP_COVER_MAX_BYTES,
    CompanyStatus,
)
from app.modules.companies.schemas import (
    CompanyListResponse,
    CompanyResponse,
    CreateCompanyRequest,
    CreateRoadmapItemRequest,
    ReorderRoadmapRequest,
    RoadmapItemResponse,
    UpdateCompanyRequest,
    UpdatePriceRequest,
    UpdateRoadmapItemRequest,
)
from app.modules.companies.service import (
    build_roadmap_item_response,
    create_company,
    create_roadmap_item,
    delete_roadmap_cover,
    delete_roadmap_item,
    list_companies,
    reorder_roadmap,
    set_roadmap_cover,
    update_company,
    update_price,
    update_roadmap_item,
    validate_roadmap_cover_mime_by_filename,
)
from app.modules.staff.constants import is_admin
from app.modules.staff.permissions import require_financial_operations
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/companies", tags=["staff-companies"])


# ---------------------------------------------------------------------------
# Company CRUD
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=CompanyListResponse,
)
async def list_companies_endpoint(
    company_status: CompanyStatus | None = Query(
        default=None,
        alias="status",
        description=(
            "Filter by lifecycle status: active, hidden, or archived. "
            "Unknown values rejected with 422."
        ),
    ),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_reader),
) -> CompanyListResponse:
    """List all companies (active / hidden / archived) with pagination.

    Filter precedence: when ?status= is supplied the service uses that
    exact value; otherwise the staff list returns every status (the
    service-layer active_only flag is forced to False here so the
    public-flow default never leaks into the staff view).

    ?search= does a case-insensitive substring match on
    CompanyProfile.name; the service escapes LIKE metacharacters so
    `%`, `_`, `\\` in the needle match literally.

    iter 2.6c B2: the `status` parameter is bound as CompanyStatus at
    the FastAPI boundary -- unknown values are rejected with 422
    before reaching the service. The Python identifier is renamed
    to `company_status` so we do not shadow the `fastapi.status`
    module imported at the top of this file.
    """
    companies, total = await list_companies(
        session,
        active_only=False,
        status=company_status.value if company_status is not None else None,
        search=search,
        page=page,
        per_page=per_page,
    )
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_company_endpoint(
    body: CreateCompanyRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Create a new company (user + profile).

    Requires: company_manage + financial_operations.
    """
    await require_financial_operations(staff, session)

    profile = await create_company(body, staff, session)
    return CompanyResponse.model_validate(profile)


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
)
async def update_company_endpoint(
    company_id: UUID,
    body: UpdateCompanyRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Update company profile.

    If distribution_config is in the body, also requires financial_operations.
    """
    updates = body.model_dump(exclude_unset=True)
    if "distribution_config" in updates:
        await require_financial_operations(staff, session)

    profile = await update_company(company_id, body, staff, session)
    return CompanyResponse.model_validate(profile)


@router.patch(
    "/{company_id}/price",
    response_model=CompanyResponse,
)
async def update_price_endpoint(
    company_id: UUID,
    body: UpdatePriceRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> CompanyResponse:
    """Change company share price.

    Requires: company_manage + financial_operations.
    Cascades to active/hidden products.
    """
    await require_financial_operations(staff, session)

    profile = await update_price(company_id, body.price_per_unit_cents, staff, session)
    return CompanyResponse.model_validate(profile)


# ---------------------------------------------------------------------------
# Roadmap CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/{company_id}/roadmap",
    response_model=RoadmapItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_roadmap_item_endpoint(
    company_id: UUID,
    body: CreateRoadmapItemRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Add a roadmap item (R1 §5). Per-kind validation handled by the
    request schema; service rejects cross-company linked products and
    missing posts."""
    item = await create_roadmap_item(
        company_id,
        body.title,
        staff,
        session,
        kind=body.kind.value,
        description=body.description,
        target_date=body.target_date,
        valid_until=body.valid_until,
        status=body.status,
        external_url=body.external_url,
        post_id=body.post_id,
        linked_product_id=body.linked_product_id,
    )
    # Freshly-created items have no cover and no resolved post yet
    # (post snippet is resolved at detail-render time). Pass None for
    # the post argument; the helper handles it.
    return await build_roadmap_item_response(item, None, session)


# NOTE: reorder MUST be declared before {item_id} routes to prevent
# FastAPI from matching "reorder" as a UUID path parameter.
@router.patch(
    "/{company_id}/roadmap/reorder",
    response_model=list[RoadmapItemResponse],
)
async def reorder_roadmap_endpoint(
    company_id: UUID,
    body: ReorderRoadmapRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> list[RoadmapItemResponse]:
    """Reorder roadmap items."""
    items = await reorder_roadmap(company_id, body.item_ids, staff, session)
    # Use the build helper so the response keeps cover_url consistent
    # with the detail endpoint. Post snippets are not embedded on
    # reorder (the operation does not change post links); frontend
    # refetches the detail view if a post embed is needed.
    return [
        await build_roadmap_item_response(item, None, session)
        for item in items
    ]


@router.patch(
    "/{company_id}/roadmap/{item_id}",
    response_model=RoadmapItemResponse,
)
async def update_roadmap_item_endpoint(
    company_id: UUID,
    item_id: UUID,
    body: UpdateRoadmapItemRequest,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Update a roadmap item (partial, R1 §5).

    Sentinel `...` distinguishes "field absent from PATCH body" (keep
    current value) from "explicitly null" (clear the field). The
    service applies the milestone state-machine check before any
    write.
    """
    updates = body.model_dump(exclude_unset=True)

    item = await update_roadmap_item(
        company_id,
        item_id,
        staff,
        session,
        title=updates.get("title"),
        description=updates.get("description", ...),
        target_date=updates.get("target_date", ...),
        valid_until=updates.get("valid_until", ...),
        status=updates.get("status"),
        external_url=updates.get("external_url", ...),
        post_id=updates.get("post_id", ...),
        linked_product_id=updates.get("linked_product_id", ...),
    )
    # Post snippet not embedded here (single-item response, frontend
    # refetches the detail view if needed for the new post link).
    return await build_roadmap_item_response(item, None, session)


@router.delete(
    "/{company_id}/roadmap/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_roadmap_item_endpoint(
    company_id: UUID,
    item_id: UUID,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete a roadmap item."""
    await delete_roadmap_item(company_id, item_id, staff, session)


# ---------------------------------------------------------------------------
# Roadmap cover image (iter 2.4 R1 §5)
# ---------------------------------------------------------------------------


def _resolve_upload_size(file: UploadFile) -> int:
    """Return the upload's size without reading the body into memory.

    Mirrors attachments_staff_router._resolve_upload_size: prefer the
    Starlette-parsed UploadFile.size (from the multipart Content-Length
    header); fall back to seek/tell on the SpooledTemporaryFile when
    Starlette could not derive a size; surface 0 as the conservative
    default if even that is unavailable -- the storage layer will then
    reject the upload via the bucket-level body limit.
    """
    if file.size is not None:
        return file.size

    handle = file.file
    try:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(0)
        return size
    except (OSError, AttributeError):
        return 0


@router.put(
    "/{company_id}/roadmap/{item_id}/cover",
    response_model=RoadmapItemResponse,
)
async def set_roadmap_cover_endpoint(
    company_id: UUID,
    item_id: UUID,
    file: UploadFile = File(...),
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Upload / replace the cover image for a roadmap item (R1 §5).

    PUT semantics -- repeated calls overwrite. Mime is derived from
    the filename extension (PNG / JPEG / WEBP); the multipart
    Content-Type header sent by the client is ignored to neutralise
    spoofed-mime stored-XSS attacks (mirrors attachments staff router).

    Size limit is enforced here (BadRequestError -> 400) before the
    bytes reach the storage layer.
    """
    original_filename = file.filename or "untitled"
    content_type, ext = validate_roadmap_cover_mime_by_filename(
        original_filename
    )
    file_size_bytes = _resolve_upload_size(file)
    if file_size_bytes > ROADMAP_COVER_MAX_BYTES:
        raise BadRequestError(
            f"Cover image exceeds {ROADMAP_COVER_MAX_BYTES} bytes "
            f"({file_size_bytes} given)"
        )

    item = await set_roadmap_cover(
        session=session,
        company_id=company_id,
        item_id=item_id,
        staff=staff,
        file_data=file.file,
        file_size_bytes=file_size_bytes,
        content_type=content_type,
        file_extension=ext,
    )
    # Post snippet not embedded -- the endpoint is per-item and does
    # not change the post link; frontend refetches detail when it
    # needs the embedded post.
    return await build_roadmap_item_response(item, None, session)


@router.delete(
    "/{company_id}/roadmap/{item_id}/cover",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_roadmap_cover_endpoint(
    company_id: UUID,
    item_id: UUID,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Remove the cover image from a roadmap item.

    404 when no cover is set -- the operation is explicit so the UI
    knows it was a no-op instead of treating empty cover as success.
    """
    await delete_roadmap_cover(company_id, item_id, staff, session)
