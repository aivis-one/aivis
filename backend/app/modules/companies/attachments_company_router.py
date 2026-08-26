# =============================================================================
# AIVIS.ONE Backend -- Company Attachments Self-Service Router (TASK-30)
# =============================================================================
#
# ENDPOINTS (no hard-delete on this surface -- see the module-level note
#            near the bottom of this docstring):
#   GET    /api/v1/company/attachments
#          ?category=&category_prefix=&language=
#       -> list[AttachmentResponse]                                     (200)
#   POST   /api/v1/company/attachments
#          (multipart: metadata=<json>, file=<binary>)
#       -> AttachmentResponse                                            (201)
#   PATCH  /api/v1/company/attachments/reorder
#          (json: ReorderAttachmentsRequest)
#       -> 204
#   PATCH  /api/v1/company/attachments/{attachment_id}
#          (json: AttachmentPatchBody)
#       -> AttachmentResponse                                            (200)
#   PATCH  /api/v1/company/attachments/{attachment_id}/replace
#          (multipart: file=<binary>)
#       -> AttachmentResponse                                            (200)
#   DELETE /api/v1/company/attachments/{attachment_id}
#       -> 204
#
# TASK-30-SPEC.md §4 lists "attachments / images" under the set of things
# a project may edit about itself. Mirrors roadmap_company_router.py's
# shape exactly: no {company_id} anywhere in these URLs -- every write is
# hard-scoped to the caller's OWN company_id, resolved server-side from
# the auth token via get_current_company_profile (companies/dependencies.py),
# so a project can never address another company's attachment row through
# this surface (the isolation guarantee is structural, not a runtime
# ownership check that could be forgotten).
#
# Request/response schemas are the SAME AttachmentInboxMetadata /
# AttachmentPatchBody / ReorderAttachmentsRequest / AttachmentResponse
# types the staff (attachments_staff_router.py) and auth-flow
# (attachments_router.py) surfaces use -- none of them carry company_id
# or any staff-only field. The response type is the plain AttachmentResponse
# (NOT StaffAttachmentResponse): storage_key is an internal MinIO path
# with no operational meaning to the project itself (downloads go through
# the presigned-URL endpoint on attachments_router.py, not the raw key),
# created_by_id is audit-only identity the project already knows (it's
# always themselves on this surface), and is_deleted is always False for
# what this endpoint returns (soft-deleted rows are filtered by default,
# same as the auth-flow list).
#
# WRITE LOGIC:
#   companies/service.py's create_own_attachment / patch_own_attachment_metadata /
#   replace_own_attachment_file / soft_delete_own_attachment /
#   reorder_own_attachments mirror the staff-side functions' validation
#   and storage flow exactly, but audit target_type="company" /
#   actor_type="user" instead of target_type="attachment" (or "company"
#   for reorder) / actor_type="staff" -- see the section docstring above
#   those functions in service.py for why they are separate functions
#   rather than thin wrappers (same reasoning posts/service.py documents
#   for create_company_post et al., and roadmap_company_router.py restates
#   for this same feature).
#
# NO HARD DELETE (Q-ATT-1, restated for self-service):
#   attachments_staff_router.py's hard-delete endpoint requires project_manage
#   PLUS a full is_admin() check specifically because it is irreversible
#   (drops the row AND the MinIO object) -- its own docstring notes that
#   "soft-delete is sufficient for almost every operational case" even
#   for staff. A project has no admin-equivalent escalation path to
#   recover from its own mistake the way staff can hand a hard-delete
#   decision to an admin, so this surface deliberately exposes
#   soft_delete_own_attachment() only. There is no
#   `DELETE .../{attachment_id}/hard` route declared anywhere below --
#   not merely unauthorized, genuinely unroutable (a request to that path
#   404s the same way any unmatched route would). Verified by
#   tests/test_company_attachments.py.
#
# MULTIPART FORMAT / MIME WHITELIST / SIZE LIMIT:
#   Identical contract to attachments_staff_router.py -- see that
#   module's docstring for the full rationale (metadata as a JSON Form
#   field validated via AttachmentInboxMetadata.model_validate_json(),
#   extension-based MIME validation via validate_attachment_mime_by_filename,
#   streamed multipart upload via UploadFile.file, 100MB cap enforced by
#   Nginx). Not repeated here.
#
# SESSION SAFETY:
#   get_current_company_profile (companies/dependencies.py) is wired to
#   get_db_reader -- a rollback-only session, same as GET /companies/me.
#   Every write endpoint below only reads `company.id` / `company.user_id`
#   (plain UUID scalars already loaded on the object, not lazy relations)
#   off that dependency and passes them into the service functions, which
#   re-load the CompanyAttachment / CompanyProfile rows against THIS
#   request's own get_db_session-bound writer session. Mirrors
#   update_own_company's documented "id + re-load, never the raw
#   dependency object" pattern (companies/router.py SESSION NOTE) and
#   roadmap_company_router.py's restatement of it.
#
# AUTH:
#   All endpoints require role=company via get_current_company_profile,
#   which 403s any caller without a CompanyProfile.
#
# AUDIT:
#   record_audit(target_type="company", target_id=<own company_id>) on
#   every write, so these show up in
#   GET /api/v1/staff/audit/companies?company_id=<id> -- the same
#   convention update_own_company, posts/company_router.py, and
#   roadmap_company_router.py established.
#
# COMMIT RULE (P-01):
#   Router never calls session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.companies.models import CompanyProfile
from app.modules.companies.schemas import (
    AttachmentInboxMetadata,
    AttachmentPatchBody,
    AttachmentResponse,
    ReorderAttachmentsRequest,
)
from app.modules.companies.service import (
    create_own_attachment,
    list_attachments,
    patch_own_attachment_metadata,
    reorder_own_attachments,
    replace_own_attachment_file,
    soft_delete_own_attachment,
    validate_attachment_mime_by_filename,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/company/attachments", tags=["company-attachments"])


def _resolve_upload_size(file: UploadFile) -> int:
    """Return the upload's size without reading the body into memory.

    Duplicated from attachments_staff_router.py's helper of the same name
    -- each router keeps its own copy by existing project convention
    (see roadmap_company_router.py's identical helper) rather than
    importing a private helper across router modules.
    """
    if file.size is not None:
        return file.size

    handle = file.file
    try:
        handle.seek(0, 2)  # end of file
        size = handle.tell()
        handle.seek(0)  # rewind for the streaming upload
        return size
    except (OSError, AttributeError):
        return 0


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[AttachmentResponse],
)
async def list_own_attachments_endpoint(
    category: str | None = Query(default=None),
    category_prefix: str | None = Query(default=None),
    language: str | None = Query(default=None),
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_reader),
) -> list[AttachmentResponse]:
    """List the caller's own non-deleted attachments.

    Unlike the staff list, there is no `include_deleted` toggle -- a
    project has no restore capability on this surface (mirrors "no
    hard-delete" above: the trash view is a staff/admin concept). Every
    non-deleted row is returned regardless of is_published / is_public --
    the project needs to see its own drafts, not just what investors
    currently see.
    """
    items = await list_attachments(
        session,
        company.id,
        category=category,
        category_prefix=category_prefix,
        language=language,
    )
    return [AttachmentResponse.model_validate(item) for item in items]


# ---------------------------------------------------------------------------
# Create (multipart: file + metadata)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_own_attachment_endpoint(
    metadata: str = Form(...),
    file: UploadFile = File(...),
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> AttachmentResponse:
    """Upload a new attachment on the caller's own company via multipart.

    The `metadata` form field is a JSON string conforming to
    AttachmentInboxMetadata -- same schema the staff multipart create and
    the inbox/reconcile flow use.
    """
    metadata_obj = AttachmentInboxMetadata.model_validate_json(metadata)
    original_filename = file.filename or "untitled"
    content_type = validate_attachment_mime_by_filename(original_filename)
    file_size_bytes = _resolve_upload_size(file)

    attachment = await create_own_attachment(
        session=session,
        company_id=company.id,
        actor_user_id=company.user_id,
        file_data=file.file,
        file_size_bytes=file_size_bytes,
        original_filename=original_filename,
        content_type=content_type,
        metadata=metadata_obj,
    )
    return AttachmentResponse.model_validate(attachment)


# ---------------------------------------------------------------------------
# Reorder (bulk)
# ---------------------------------------------------------------------------
#
# NOTE: this route MUST be declared before /{attachment_id} routes below.
# Otherwise FastAPI tries to parse "reorder" as a UUID for the
# attachment_id path parameter and 422s the request. Mirrors the same
# ordering requirement in attachments_staff_router.py and
# roadmap_company_router.py.


@router.patch(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reorder_own_attachments_endpoint(
    body: ReorderAttachmentsRequest,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Bulk reorder the caller's own attachments inside one category.

    Body is an exact list of every non-deleted attachment id in
    (own company_id, category); the service rejects partial / extended
    lists with 400. Returns 204 -- same shape as the staff reorder
    endpoint (attachments_staff_router.py), unlike the roadmap
    self-service reorder which returns the reordered list; kept
    consistent with this endpoint's direct staff sibling on the same
    resource rather than the roadmap surface's differing convention.
    """
    await reorder_own_attachments(
        session,
        company.id,
        body.category,
        body.item_ids,
        company.user_id,
    )


# ---------------------------------------------------------------------------
# Patch metadata
# ---------------------------------------------------------------------------


@router.patch(
    "/{attachment_id}",
    response_model=AttachmentResponse,
)
async def patch_own_attachment_endpoint(
    attachment_id: UUID,
    body: AttachmentPatchBody,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> AttachmentResponse:
    """Partial update of an own attachment's metadata. JSON body, no file.

    404s (never 403) if `attachment_id` belongs to a different company --
    see get_attachment in companies/service.py, same isolation contract
    as attachments_staff_router.py and roadmap_company_router.py.
    """
    attachment = await patch_own_attachment_metadata(
        session, company.id, attachment_id, body, company.user_id
    )
    return AttachmentResponse.model_validate(attachment)


# ---------------------------------------------------------------------------
# Replace file (multipart, file-only)
# ---------------------------------------------------------------------------


@router.patch(
    "/{attachment_id}/replace",
    response_model=AttachmentResponse,
)
async def replace_own_attachment_endpoint(
    attachment_id: UUID,
    file: UploadFile = File(...),
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> AttachmentResponse:
    """Swap the binary content of an own attachment. Metadata untouched.

    404 (never 403) on cross-company attachment_id.
    """
    original_filename = file.filename or "untitled"
    content_type = validate_attachment_mime_by_filename(original_filename)
    file_size_bytes = _resolve_upload_size(file)

    attachment = await replace_own_attachment_file(
        session=session,
        company_id=company.id,
        attachment_id=attachment_id,
        actor_user_id=company.user_id,
        file_data=file.file,
        file_size_bytes=file_size_bytes,
        original_filename=original_filename,
        content_type=content_type,
    )
    return AttachmentResponse.model_validate(attachment)


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def soft_delete_own_attachment_endpoint(
    attachment_id: UUID,
    company: CompanyProfile = Depends(get_current_company_profile),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Mark an own attachment as deleted (is_deleted=True). MinIO object
    stays. 404 (never 403) on cross-company attachment_id.

    No hard-delete counterpart exists on this router -- see the module
    docstring.
    """
    await soft_delete_own_attachment(
        session, company.id, attachment_id, company.user_id
    )
