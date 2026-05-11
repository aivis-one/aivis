# =============================================================================
# CBSHOME Backend -- Company Attachments Auth Router (Refactor 2 iter 2.2)
# =============================================================================
#
# ENDPOINTS:
#   GET /api/v1/companies/{company_id}/attachments
#       -> list[AttachmentResponse]                                       (200)
#   GET /api/v1/companies/{company_id}/attachments/{att_id}/download
#       -> 302 Location: <presigned URL>                                  (302)
#
# AUTH:
#   Both endpoints require an authenticated user (any role) via
#   get_current_user. R2 §3.3 frames the audience as investor + agent,
#   but the gate stays "any auth" -- staff and the company-itself caller
#   also have legitimate read paths through these URLs and the response
#   schema (AttachmentResponse) hides the operational fields anyway.
#
# FILTERS (R2 §3.3 + §3.6):
#   ?category=X         -- exact path-tree match
#   ?category_prefix=Y  -- LIKE prefix% (Staff-typed metacharacters
#                          are escaped server-side)
#   ?language=Z         -- exact ISO 639-1 code; omitting the param
#                          returns every language. iter 2.4-post
#                          mini-fix removed NULL semantics from the
#                          column -- 'en' is the universal fallback.
#
# VISIBILITY:
#   List + download both require is_published = True AND is_deleted = False.
#   A 404 (not 403) on a hidden / deleted / cross-company attachment matches
#   the public-flow contract and avoids confirming existence.
#
# COMMIT RULE (P-01):
#   Read-only endpoints, get_db_reader. No commits.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
from app.core.storage import generate_presigned_url
from app.modules.auth.dependencies import get_current_user
from app.modules.companies.schemas import AttachmentResponse
from app.modules.companies.service import (
    get_attachment,
    get_company,
    list_attachments,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/companies",
    tags=["company-attachments"],
)


@router.get(
    "/{company_id}/attachments",
    response_model=list[AttachmentResponse],
)
async def list_attachments_endpoint(
    company_id: UUID,
    category: str | None = Query(default=None),
    category_prefix: str | None = Query(default=None),
    language: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> list[AttachmentResponse]:
    """List published, non-deleted attachments for the given company.

    Returns AttachmentResponse (no storage_key, created_by, is_deleted).
    Use the dedicated download endpoint to actually retrieve the bytes --
    presigned URLs are not embedded in the list payload to keep the list
    cacheable and the URLs short-lived.
    """
    # Surface a 404 if the company itself doesn't exist, before exposing
    # the (empty) attachments list. Mirrors the public companies endpoint.
    await get_company(company_id, session)

    items = await list_attachments(
        session,
        company_id,
        category=category,
        category_prefix=category_prefix,
        language=language,
        only_published=True,
    )
    return [AttachmentResponse.model_validate(item) for item in items]


@router.get(
    "/{company_id}/attachments/{attachment_id}/download",
    status_code=status.HTTP_302_FOUND,
)
async def download_attachment_endpoint(
    company_id: UUID,
    attachment_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> RedirectResponse:
    """Issue a 302 redirect to a presigned MinIO URL.

    TTL is settings.minio_presigned_ttl_auth (default 900s = 15 min).
    Hidden / deleted / cross-company attachments return 404 -- never
    302 -- so the auth-flow contract matches the list filter.
    """
    attachment = await get_attachment(session, company_id, attachment_id)

    # Mirror the list filter: investors can't pull a private (unpublished)
    # file by guessing the URL.
    if not attachment.is_published:
        raise NotFoundError("Attachment not found")

    # Round 4 (SEC-01): force-download via Content-Disposition: attachment.
    # Closes the SVG-as-XSS vector -- the browser saves the file to disk
    # instead of executing any active content inside it.
    url = await generate_presigned_url(
        attachment.storage_key,
        ttl_seconds=settings.minio_presigned_ttl_auth,
        download_filename=attachment.original_filename,
    )

    logger.info(
        "attachment_download_presigned",
        attachment_id=str(attachment.id),
        company_id=str(company_id),
        user_id=str(user.id),
        ttl_seconds=settings.minio_presigned_ttl_auth,
    )

    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
