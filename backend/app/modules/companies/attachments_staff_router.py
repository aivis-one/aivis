# =============================================================================
# CBSHOME Backend -- Company Attachments Staff Router (Refactor 2 iter 2.2)
# =============================================================================
#
# ENDPOINTS (all require company_manage; hard-delete also requires admin):
#   GET    /api/v1/staff/companies/{id}/attachments?include_deleted=
#       -> list[StaffAttachmentResponse]                                   (200)
#   POST   /api/v1/staff/companies/{id}/attachments
#          (multipart: metadata=<json>, file=<binary>)
#       -> StaffAttachmentResponse                                          (201)
#   PATCH  /api/v1/staff/companies/{id}/attachments/{att_id}
#          (json: AttachmentPatchBody)
#       -> StaffAttachmentResponse                                          (200)
#   PATCH  /api/v1/staff/companies/{id}/attachments/{att_id}/replace
#          (multipart: file=<binary>)
#       -> StaffAttachmentResponse                                          (200)
#   DELETE /api/v1/staff/companies/{id}/attachments/{att_id}
#       -> 204
#   DELETE /api/v1/staff/companies/{id}/attachments/{att_id}/hard
#       -> 204                                                       (admin only)
#
# PERMISSIONS:
#   - All 6 endpoints: require_staff_permission("company_manage").
#   - Hard delete additionally calls _require_admin(): is_admin checks
#     that every permission flag is True, matching staff/router.py
#     where _require_admin lives. Q-ATT-1: hard delete is a destructive
#     irreversible operation that drops both the row and the MinIO
#     object, so it sits behind the admin gate even though regular
#     soft-delete is sufficient for almost every operational case.
#
# MULTIPART FORMAT (R2 §3.7):
#   metadata is a JSON string in a Form field (NOT a Pydantic model
#   directly -- FastAPI cannot mix Form + JSON body in one route).
#   We parse it via AttachmentInboxMetadata.model_validate_json() so the
#   inbox flow (cbsmeta.json) and the multipart flow share one schema.
#
# MIME WHITELIST (Round 4 SEC-01 / QC-02):
#   ALLOWED_ATTACHMENT_MIME_TYPES (companies/constants.py). Validated by
#   filename extension via companies.service.validate_attachment_mime_by_filename
#   -- 400 BadRequest before the bytes touch MinIO. We deliberately do
#   NOT trust file.content_type (multipart header from the client), so a
#   request claiming "application/pdf" while uploading evil.svg gets
#   rejected by extension. The reconcile script reuses the same helper.
#   Defence-in-depth: download endpoints add Content-Disposition:
#   attachment to the presigned URL so the browser saves rather than
#   renders, neutralising stored-XSS even if a bad payload sneaks past
#   extension validation.
#
# 100MB SIZE LIMIT (R2 Q-ATT-3):
#   Enforced by Nginx (client_max_body_size 100m) at the proxy layer.
#   Round 4 (PERF-01): the router no longer materialises the whole
#   payload into a Python `bytes` (the previous `await file.read()`
#   peaked RAM at N * 100 MB for N parallel uploads). We now stream
#   the SpooledTemporaryFile straight to MinIO via boto3 put_object,
#   with an explicit Content-Length pulled from UploadFile.size.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import require_staff_permission
from app.modules.companies.schemas import (
    AttachmentInboxMetadata,
    AttachmentPatchBody,
    StaffAttachmentResponse,
)
from app.modules.companies.service import (
    create_attachment,
    get_company,
    hard_delete_attachment,
    list_attachments,
    patch_attachment_metadata,
    replace_attachment_file,
    soft_delete_attachment,
    validate_attachment_mime_by_filename,
)
from app.modules.staff.constants import is_admin
from app.modules.staff.service import (
    get_effective_permissions,
    get_staff_profile,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/staff/companies",
    tags=["staff-company-attachments"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_admin(staff: User, session: AsyncSession) -> None:
    """Ensure the staff member has the admin marker (every permission True).

    Mirrors staff/router.py::_require_admin so the policy stays in
    lockstep across the codebase. Raises ForbiddenError otherwise.
    """
    profile = await get_staff_profile(staff.id, session)
    if profile is None:
        raise ForbiddenError("Staff profile not found")

    effective = get_effective_permissions(profile)
    if not is_admin(effective):
        raise ForbiddenError("Admin access required")


def _resolve_upload_size(file: UploadFile) -> int:
    """Return the upload's size without reading the body into memory.

    Round 4 (PERF-01): three-step fallback so we get a Content-Length
    for MinIO without buffering 100 MB into a Python `bytes`:
      1. UploadFile.size -- Starlette parses the multipart Content-Length
         header and exposes it directly. Almost always present.
      2. If absent, seek to end of the SpooledTemporaryFile and tell the
         offset. Cheap (no copy) for both in-memory and on-disk spool
         backings. Reset the pointer to the start before returning.
      3. If even that fails (rare -- non-seekable underlying handle), 0
         is the only safe default; MinIO will reject the upload via the
         configured Content-Length / max-body limit.
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
    "/{company_id}/attachments",
    response_model=list[StaffAttachmentResponse],
)
async def list_attachments_staff_endpoint(
    company_id: UUID,
    include_deleted: bool = Query(default=False),
    category: str | None = Query(default=None),
    category_prefix: str | None = Query(default=None),
    language: str | None = Query(default=None),
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_reader),
) -> list[StaffAttachmentResponse]:
    """Staff list of attachments. Sees everything regardless of publish flags.

    Soft-deleted rows are hidden by default; pass include_deleted=true
    to surface them (used by the Staff trash / restore UI).
    """
    await get_company(company_id, session)

    items = await list_attachments(
        session,
        company_id,
        category=category,
        category_prefix=category_prefix,
        language=language,
        include_deleted=include_deleted,
    )
    return [StaffAttachmentResponse.model_validate(item) for item in items]


# ---------------------------------------------------------------------------
# Create (multipart: file + metadata)
# ---------------------------------------------------------------------------


@router.post(
    "/{company_id}/attachments",
    response_model=StaffAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_attachment_staff_endpoint(
    company_id: UUID,
    metadata: str = Form(...),
    file: UploadFile = File(...),
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> StaffAttachmentResponse:
    """Upload a new attachment via multipart.

    The `metadata` form field is a JSON string conforming to
    AttachmentInboxMetadata (the same schema reconcile_attachments
    parses out of cbsmeta.json -- one schema, two transport surfaces).
    """
    metadata_obj = AttachmentInboxMetadata.model_validate_json(metadata)
    # Round 4 (SEC-01 / QC-02): validate by extension, not by client-
    # supplied multipart Content-Type. The filename is what reaches the
    # router from the browser/curl; spoofing a different MIME header
    # while keeping a real extension was the original attack vector.
    original_filename = file.filename or "untitled"
    content_type = validate_attachment_mime_by_filename(original_filename)
    # Round 4 (PERF-01): stream the body straight to MinIO instead of
    # reading the whole 100 MB upload into memory. Starlette exposes the
    # underlying SpooledTemporaryFile via UploadFile.file, with the file
    # pointer already at the start of the payload after multipart parsing.
    # We rely on UploadFile.size (set from the multipart Content-Length)
    # to fill in the explicit ContentLength header; if absent we measure
    # via seek/tell (no read).
    file_size_bytes = _resolve_upload_size(file)

    attachment = await create_attachment(
        session=session,
        company_id=company_id,
        staff=staff,
        file_data=file.file,
        file_size_bytes=file_size_bytes,
        original_filename=original_filename,
        content_type=content_type,
        metadata=metadata_obj,
    )
    return StaffAttachmentResponse.model_validate(attachment)


# ---------------------------------------------------------------------------
# Patch metadata
# ---------------------------------------------------------------------------


@router.patch(
    "/{company_id}/attachments/{attachment_id}",
    response_model=StaffAttachmentResponse,
)
async def patch_attachment_staff_endpoint(
    company_id: UUID,
    attachment_id: UUID,
    body: AttachmentPatchBody,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> StaffAttachmentResponse:
    """Partial update of attachment metadata. JSON body, no file upload."""
    attachment = await patch_attachment_metadata(
        session, company_id, attachment_id, body, staff
    )
    return StaffAttachmentResponse.model_validate(attachment)


# ---------------------------------------------------------------------------
# Replace file (multipart, file-only)
# ---------------------------------------------------------------------------


@router.patch(
    "/{company_id}/attachments/{attachment_id}/replace",
    response_model=StaffAttachmentResponse,
)
async def replace_attachment_staff_endpoint(
    company_id: UUID,
    attachment_id: UUID,
    file: UploadFile = File(...),
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> StaffAttachmentResponse:
    """Swap the binary content of an existing attachment.

    Metadata stays untouched -- title / category / publish flags carry
    over. Use the regular PATCH endpoint when only metadata changes.
    """
    # Round 4 (SEC-01 / QC-02): same extension-based validation as the
    # POST endpoint. See create_attachment_staff_endpoint for rationale.
    original_filename = file.filename or "untitled"
    content_type = validate_attachment_mime_by_filename(original_filename)
    # Round 4 (PERF-01): stream-pass like in POST.
    file_size_bytes = _resolve_upload_size(file)

    attachment = await replace_attachment_file(
        session=session,
        company_id=company_id,
        attachment_id=attachment_id,
        staff=staff,
        file_data=file.file,
        file_size_bytes=file_size_bytes,
        original_filename=original_filename,
        content_type=content_type,
    )
    return StaffAttachmentResponse.model_validate(attachment)


# ---------------------------------------------------------------------------
# Soft delete
# ---------------------------------------------------------------------------


@router.delete(
    "/{company_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def soft_delete_attachment_staff_endpoint(
    company_id: UUID,
    attachment_id: UUID,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Mark the attachment as deleted (is_deleted=True). MinIO object stays."""
    await soft_delete_attachment(session, company_id, attachment_id, staff)


# ---------------------------------------------------------------------------
# Hard delete (admin only)
# ---------------------------------------------------------------------------


@router.delete(
    "/{company_id}/attachments/{attachment_id}/hard",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def hard_delete_attachment_staff_endpoint(
    company_id: UUID,
    attachment_id: UUID,
    staff: User = Depends(require_staff_permission("company_manage")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Drop the row AND the MinIO object. Admin-only.

    Operates on rows regardless of is_deleted, so admins can finalise a
    deletion that staff already started.
    """
    await _require_admin(staff, session)
    await hard_delete_attachment(session, company_id, attachment_id, staff)
