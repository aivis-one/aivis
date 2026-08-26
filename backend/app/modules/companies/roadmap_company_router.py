# =============================================================================
# AIVIS.ONE Backend -- Company Roadmap Self-Service Router (TASK-30)
# =============================================================================
#
# ENDPOINTS:
#   GET    /api/v1/company/roadmap                -- list the caller's own
#                                                      non-deleted roadmap
#                                                      items, in order
#   POST   /api/v1/company/roadmap                -- add a roadmap item
#   PATCH  /api/v1/company/roadmap/reorder         -- reorder own items
#   PATCH  /api/v1/company/roadmap/{item_id}       -- update an own item
#   DELETE /api/v1/company/roadmap/{item_id}       -- soft-delete an own item
#   PUT    /api/v1/company/roadmap/{item_id}/cover -- upload/replace cover
#   DELETE /api/v1/company/roadmap/{item_id}/cover -- remove cover
#
# TASK-30-SPEC.md §4 lists "roadmap items" under the set of things a
# project may edit about itself. Mirrors posts/company_router.py's shape
# exactly: no {company_id} anywhere in these URLs -- every write is
# hard-scoped to the caller's OWN company_id, resolved server-side from
# the auth token via get_current_company_profile (companies/dependencies.py),
# so a project can never address another company's roadmap row through
# this surface (the isolation guarantee is structural, not a runtime
# ownership check that could be forgotten).
#
# Request/response schemas are the SAME CreateRoadmapItemRequest /
# UpdateRoadmapItemRequest / ReorderRoadmapRequest / RoadmapItemResponse
# types the staff surface (staff_router.py) uses -- none of them carry
# company_id or any other admin-only field (every request type is
# extra="forbid", and the per-kind milestone/event/announcement rules
# already live in the schema layer via CreateRoadmapItemRequest's
# model_validator, not duplicated here).
#
# WRITE LOGIC:
#   companies/service.py's create_own_roadmap_item / update_own_roadmap_item /
#   delete_own_roadmap_item / reorder_own_roadmap / set_own_roadmap_cover /
#   delete_own_roadmap_cover mirror the staff-side functions' validation
#   and storage flow exactly, but audit target_type="company" /
#   actor_type="user" instead of target_type="roadmap_item" (or "company"
#   for reorder) / actor_type="staff" -- see the section docstring above
#   those functions in service.py for why they are separate functions
#   rather than thin wrappers (same reasoning posts/service.py documents
#   for create_company_post et al.).
#
# SESSION SAFETY:
#   get_current_company_profile (companies/dependencies.py) is wired to
#   get_db_reader -- a rollback-only session, same as GET /companies/me.
#   Every write endpoint below only reads `company.id` / `company.user_id`
#   (plain UUID scalars already loaded on the object, not lazy relations)
#   off that dependency and passes them into the service functions, which
#   re-load the CompanyRoadmapItem / CompanyProfile rows against THIS
#   request's own get_db_session-bound writer session. Mirrors
#   update_own_company's documented "id + re-load, never the raw
#   dependency object" pattern (companies/router.py SESSION NOTE).
#
# AUTH:
#   All endpoints require role=company via get_current_company_profile,
#   which 403s any caller without a CompanyProfile.
#
# AUDIT:
#   record_audit(target_type="company", target_id=<own company_id>) on
#   every write, so these show up in
#   GET /api/v1/staff/audit/companies?company_id=<id> -- the same
#   convention update_own_company and posts/company_router.py established.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import BadRequestError
from app.modules.companies.constants import ROADMAP_COVER_MAX_BYTES
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.companies.schemas import (
    CreateRoadmapItemRequest,
    ReorderRoadmapRequest,
    RoadmapItemResponse,
    UpdateRoadmapItemRequest,
)
from app.modules.companies.service import (
    build_roadmap_item_response,
    create_own_roadmap_item,
    delete_own_roadmap_cover,
    delete_own_roadmap_item,
    get_company_detail,
    reorder_own_roadmap,
    set_own_roadmap_cover,
    update_own_roadmap_item,
    validate_roadmap_cover_mime_by_filename,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/company/roadmap", tags=["company-roadmap"])


def _resolve_upload_size(file: UploadFile) -> int:
    """Return the upload's size without reading the body into memory.

    Duplicated from staff_router.py's helper of the same name (itself a
    mirror of attachments_staff_router's) -- each router keeps its own
    copy by existing project convention rather than importing a private
    helper across router modules.
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


@router.get(
    "",
    response_model=list[RoadmapItemResponse],
)
async def list_own_roadmap_endpoint(
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_reader),
) -> list[RoadmapItemResponse]:
    """List the caller's own non-deleted roadmap items, in display order.

    Reuses get_company_detail -- the same assembly the staff detail
    endpoint and the public detail endpoint use -- scoped to the
    caller's own company_id. No {company_id} path parameter exists
    on this surface at all.
    """
    _profile, roadmap_items, posts_map = await get_company_detail(company.id, session)
    return [
        await build_roadmap_item_response(item, posts_map.get(item.post_id), session)
        for item in roadmap_items
    ]


@router.post(
    "",
    response_model=RoadmapItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_own_roadmap_item_endpoint(
    body: CreateRoadmapItemRequest,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Add a roadmap item to the caller's own company.

    Per-kind validation is enforced by CreateRoadmapItemRequest's
    model_validator -- identical rules to the staff-side create.
    """
    item = await create_own_roadmap_item(
        company.id,
        company.user_id,
        body.title,
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
    return await build_roadmap_item_response(item, None, session)


# NOTE: reorder MUST be declared before {item_id} routes to prevent
# FastAPI from matching "reorder" as a UUID path parameter (same
# ordering requirement as staff_router.py).
@router.patch(
    "/reorder",
    response_model=list[RoadmapItemResponse],
)
async def reorder_own_roadmap_endpoint(
    body: ReorderRoadmapRequest,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> list[RoadmapItemResponse]:
    """Reorder the caller's own roadmap items."""
    items = await reorder_own_roadmap(company.id, body.item_ids, company.user_id, session)
    return [await build_roadmap_item_response(item, None, session) for item in items]


@router.patch(
    "/{item_id}",
    response_model=RoadmapItemResponse,
)
async def update_own_roadmap_item_endpoint(
    item_id: UUID,
    body: UpdateRoadmapItemRequest,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Partial update of an own roadmap item.

    404s (never 403) if `item_id` belongs to a different company --
    see _get_roadmap_item in companies/service.py, same isolation
    contract as companies/attachments_router.py and
    posts/company_router.py.
    """
    updates = body.model_dump(exclude_unset=True)

    item = await update_own_roadmap_item(
        company.id,
        item_id,
        company.user_id,
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
    return await build_roadmap_item_response(item, None, session)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_own_roadmap_item_endpoint(
    item_id: UUID,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Soft-delete an own roadmap item. 404 (never 403) on cross-company."""
    await delete_own_roadmap_item(company.id, item_id, company.user_id, session)


@router.put(
    "/{item_id}/cover",
    response_model=RoadmapItemResponse,
)
async def set_own_roadmap_cover_endpoint(
    item_id: UUID,
    file: UploadFile = File(...),
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> RoadmapItemResponse:
    """Upload / replace the cover image of an own roadmap item.

    Mirrors set_roadmap_cover_endpoint's mime-by-filename validation
    and size-limit check exactly -- see that endpoint's docstring in
    staff_router.py.
    """
    original_filename = file.filename or "untitled"
    content_type, ext = validate_roadmap_cover_mime_by_filename(original_filename)
    file_size_bytes = _resolve_upload_size(file)
    if file_size_bytes > ROADMAP_COVER_MAX_BYTES:
        raise BadRequestError(
            f"Cover image exceeds {ROADMAP_COVER_MAX_BYTES} bytes "
            f"({file_size_bytes} given)"
        )

    item = await set_own_roadmap_cover(
        session=session,
        company_id=company.id,
        item_id=item_id,
        actor_user_id=company.user_id,
        file_data=file.file,
        file_size_bytes=file_size_bytes,
        content_type=content_type,
        file_extension=ext,
    )
    return await build_roadmap_item_response(item, None, session)


@router.delete(
    "/{item_id}/cover",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_own_roadmap_cover_endpoint(
    item_id: UUID,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Remove the cover image from an own roadmap item. 404 if no cover."""
    await delete_own_roadmap_cover(company.id, item_id, company.user_id, session)
