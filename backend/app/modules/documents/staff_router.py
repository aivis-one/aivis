# =============================================================================
# CBSHOME Backend -- Documents Staff Router (Sprint 2.2)
# =============================================================================
#
# Staff-only endpoints for document management.
#
# ENDPOINTS:
#   POST   /api/v1/staff/documents       -- Create document (draft)
#   PATCH  /api/v1/staff/documents/{id}  -- Update document
#   DELETE /api/v1/staff/documents/{id}  -- Delete draft document
#
# AUTH:
#   All endpoints require get_current_staff (role == staff).
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.auth.dependencies import get_current_staff
from app.modules.documents.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    DocumentUpdateRequest,
)
from app.modules.documents.service import (
    create_document,
    delete_document,
    update_document,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/staff/documents", tags=["staff-documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def staff_create_document(
    body: DocumentCreateRequest,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    """Create a new document in draft status."""
    document = await create_document(staff.id, body, session)
    return DocumentResponse.model_validate(document)


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
)
async def staff_update_document(
    document_id: UUID,
    body: DocumentUpdateRequest,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentResponse:
    """Update a document (fields and/or status transition)."""
    document = await update_document(document_id, body, session)
    return DocumentResponse.model_validate(document)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def staff_delete_document(
    document_id: UUID,
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a draft document.

    Only documents in draft status can be deleted.
    Active and archived documents are preserved for audit.
    """
    await delete_document(document_id, session)
