# =============================================================================
# AIVIS.ONE Backend -- Company Attachments Public Router (Refactor 2 iter 2.2)
# =============================================================================
#
# ENDPOINTS (no auth):
#   GET /api/v1/public/companies/{company_id}/attachments
#       -> list[AttachmentResponse]                                       (200)
#   GET /api/v1/public/companies/{company_id}/attachments/{att_id}/download
#       -> 302 Location: <presigned URL>                                  (302)
#
# VISIBILITY (R2 §3.4):
#   Both endpoints require is_public = True AND is_published = True
#   AND is_deleted = False. A 404 (not 403) on anything that fails the
#   combined predicate, so guessing an attachment_id can't confirm it
#   exists privately.
#
# RATE-LIMITS PER IP (R2 Q-ATT-2):
#   list     -> PUBLIC_LIST_RATE_LIMIT     (60 / 60s)
#   download -> PUBLIC_DOWNLOAD_RATE_LIMIT (300 / 60s)
#   Counters live in Redis under keys
#       public_attach_list:<ip>
#       public_attach_dl:<ip>
#   so list and download are independent (an attacker can't burn the
#   download bucket through list spam, and vice versa).
#
# PRESIGNED URL TTL:
#   settings.minio_presigned_ttl_public (default 86400s = 24h). Long TTL
#   matches the marketing use case -- a Staff member shares the URL on
#   LinkedIn, the link must work for the rest of the day at least.
#
# COMMIT RULE (P-01):
#   Read-only endpoints, get_db_reader. No commits.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.core.database import get_db_reader
from app.core.exceptions import NotFoundError
from app.core.rate_limit import check_rate_limit
from app.core.storage import generate_presigned_url
from app.modules.companies.constants import (
    PUBLIC_DOWNLOAD_RATE_LIMIT,
    PUBLIC_LIST_RATE_LIMIT,
)
from app.modules.companies.schemas import AttachmentResponse
from app.modules.companies.service import (
    get_attachment,
    get_company,
    list_attachments,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/public/companies",
    tags=["company-attachments-public"],
)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/{company_id}/attachments",
    response_model=list[AttachmentResponse],
)
async def list_public_attachments_endpoint(
    company_id: UUID,
    request: Request,
    category: str | None = Query(default=None),
    category_prefix: str | None = Query(default=None),
    language: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_reader),
) -> list[AttachmentResponse]:
    """Public attachment list for a company. No authentication required.

    Returns only rows that are public, published, and not soft-deleted.
    Filters (category / category_prefix / language) match the auth-flow
    endpoint signature so the same Vue store can drive both views.
    """
    ip = get_client_ip(request)
    max_req, window = PUBLIC_LIST_RATE_LIMIT
    await check_rate_limit(
        f"public_attach_list:{ip}",
        max_requests=max_req,
        window_seconds=window,
        error_message="Too many requests. Please try again later.",
    )

    # Surface 404 if the company doesn't exist. Public storefront
    # already exposes company existence via /api/v1/companies, so this
    # is not new info-leak surface.
    await get_company(company_id, session)

    items = await list_attachments(
        session,
        company_id,
        category=category,
        category_prefix=category_prefix,
        language=language,
        only_published=True,
        only_public=True,
    )
    return [AttachmentResponse.model_validate(item) for item in items]


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


@router.get(
    "/{company_id}/attachments/{attachment_id}/download",
    status_code=status.HTTP_302_FOUND,
)
async def download_public_attachment_endpoint(
    company_id: UUID,
    attachment_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> RedirectResponse:
    """Issue a 302 redirect to a presigned MinIO URL. No authentication.

    TTL is settings.minio_presigned_ttl_public (default 24h). Hidden,
    private, soft-deleted, or cross-company attachments -- all return
    404 (not 403), matching R2 §3.4 so a probe can't distinguish "the
    attachment exists but is private" from "it doesn't exist".
    """
    ip = get_client_ip(request)
    max_req, window = PUBLIC_DOWNLOAD_RATE_LIMIT
    await check_rate_limit(
        f"public_attach_dl:{ip}",
        max_requests=max_req,
        window_seconds=window,
        error_message="Too many requests. Please try again later.",
    )

    attachment = await get_attachment(session, company_id, attachment_id)

    # Public-flow visibility predicate: both flags must be on, soft-delete
    # is already filtered by get_attachment(include_deleted=False default).
    if not (attachment.is_public and attachment.is_published):
        raise NotFoundError("Attachment not found")

    # Round 4 (SEC-01): force-download via Content-Disposition: attachment.
    # See attachments_router.py for rationale -- the public flow has the
    # widest blast radius (24h TTL, no auth) so the same defence applies.
    url = await generate_presigned_url(
        attachment.storage_key,
        ttl_seconds=settings.minio_presigned_ttl_public,
        download_filename=attachment.original_filename,
    )

    logger.info(
        "public_attachment_download_presigned",
        attachment_id=str(attachment.id),
        company_id=str(company_id),
        ip=ip,
        ttl_seconds=settings.minio_presigned_ttl_public,
    )

    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
