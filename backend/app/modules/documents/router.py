# =============================================================================
# AIVIS.ONE Backend -- Documents Router (Sprint 2.2 + Sprint 3.2)
# =============================================================================
#
# User-facing endpoints for document browsing and signing.
#
# ENDPOINTS:
#   GET  /api/v1/documents          -- List active documents for user's role
#   GET  /api/v1/documents/{id}     -- Get single document with is_signed
#   POST /api/v1/documents/{id}/sign -- Sign document (checkbox consent)
#
# AVATAR GUARD (Sprint 3.2, migrated to dependency layer R49):
#   sign_document_endpoint carries Depends(forbid_avatar("sign_document"))
#   to prevent staff in avatar mode from signing documents on behalf of
#   users. Same mechanism as all guarded operations (auth/avatar_guard.py).
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.documents.schemas import DocumentResponse, DocumentSigningResponse
from app.modules.documents.service import (
    get_document,
    list_documents_for_role,
    sign_document,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.get(
    "",
    response_model=list[DocumentResponse],
)
async def list_documents(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> list[DocumentResponse]:
    """List active documents for the authenticated user's role.

    Returns documents with is_signed flag indicating whether the
    user has already signed each document.
    """
    return await list_documents_for_role(
        user.role, user.language, user.id, session
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
async def get_document_detail(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> DocumentResponse:
    """Get a single document with is_signed flag."""
    return await get_document(document_id, user.id, session)


@router.post(
    "/{document_id}/sign",
    response_model=DocumentSigningResponse,
    status_code=status.HTTP_201_CREATED,
    # R49: migrated from the @require_not_avatar decorator to the
    # dependency layer -- one guard mechanism across the codebase.
    dependencies=[Depends(forbid_avatar("sign_document"))],
)
async def sign_document_endpoint(
    document_id: UUID,
    request: Request,
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentSigningResponse:
    """Sign a document (checkbox consent).

    Records the signing fact with IP address and user agent
    for compliance purposes.

    Blocked in avatar mode (Sprint 3.2, R49 dependency guard) --
    staff cannot sign documents on behalf of users.
    """
    ip_address = request.headers.get(
        "X-Real-IP",
        request.client.host if request.client else "unknown",
    )
    user_agent = request.headers.get("User-Agent", "")

    signing = await sign_document(
        user_id=user.id,
        document_id=document_id,
        ip_address=ip_address,
        user_agent=user_agent,
        session=session,
    )

    return DocumentSigningResponse.model_validate(signing)
