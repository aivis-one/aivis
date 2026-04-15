# =============================================================================
# CBSHOME Backend -- Document Service (Sprint 2.2)
# =============================================================================
#
# RESPONSIBILITIES:
#   Staff operations:
#     create_document()  -- create new document in draft status
#     update_document()  -- update document fields + status transitions
#     delete_document()  -- delete draft documents only
#
#   User operations:
#     list_documents_for_role()  -- active documents for user's role
#     get_document()             -- single document with is_signed flag
#     sign_document()            -- record checkbox consent
#
# STATUS TRANSITIONS (State Machines v1.4 section 5):
#     draft  -> active    (Staff: publish)
#     active -> draft     (Staff: unpublish for edits)
#     active -> archived  (Staff: archive)
#     draft  -> archived  (Staff: cancel draft)
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import USER_AGENT_MAX_LEN
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.documents.constants import (
    ROLE_REQUIRED_DOCUMENT_TYPES,
    VALID_STATUS_TRANSITIONS,
)
from app.modules.documents.models import (
    Document,
    DocumentSigning,
    DocumentStatus,
    DocumentType,
)
from app.modules.documents.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    DocumentUpdateRequest,
)
from app.modules.users.models import OnboardingStep, User

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Staff operations
# ---------------------------------------------------------------------------


async def create_document(
    staff_id: UUID,
    body: DocumentCreateRequest,
    session: AsyncSession,
) -> Document:
    """Create a new document in draft status.

    Raises:
        BadRequestError: If type is not a valid DocumentType.
        ConflictError: If (type, version) combination already exists.
    """
    # Validate type enum.
    valid_types = [t.value for t in DocumentType]
    if body.type not in valid_types:
        raise BadRequestError(
            f"Invalid document type: {body.type}. "
            f"Valid types: {', '.join(valid_types)}"
        )

    document = Document(
        type=body.type,
        version=body.version,
        title=body.title,
        content_url=body.content_url,
        status=DocumentStatus.DRAFT,
        created_by=staff_id,
    )
    session.add(document)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_documents_type_version" in str(exc.orig):
            raise ConflictError(
                f"Document {body.type} version {body.version} already exists"
            )
        raise

    await session.refresh(document)

    logger.info(
        "document_created",
        document_id=str(document.id),
        type=document.type,
        version=document.version,
    )

    return document


async def update_document(
    document_id: UUID,
    body: DocumentUpdateRequest,
    session: AsyncSession,
) -> Document:
    """Update a document (partial update with status transition validation).

    Raises:
        NotFoundError: If document not found.
        BadRequestError: If status transition is invalid.
    """
    stmt = select(Document).where(Document.id == document_id)
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()

    if document is None:
        raise NotFoundError("Document not found")

    updates = body.model_dump(exclude_unset=True)

    if not updates:
        return document

    # Validate status transition if status is being changed.
    if "status" in updates and updates["status"] is not None:
        new_status = updates["status"]
        allowed = VALID_STATUS_TRANSITIONS.get(document.status, [])
        if new_status not in allowed:
            raise BadRequestError(
                f"Invalid status transition: {document.status} -> {new_status}"
            )
        document.status = new_status

    # Apply other fields.
    if "title" in updates and updates["title"] is not None:
        document.title = updates["title"]
    if "content_url" in updates and updates["content_url"] is not None:
        document.content_url = updates["content_url"]

    await session.flush()
    await session.refresh(document)

    logger.info(
        "document_updated",
        document_id=str(document.id),
        updates=list(updates.keys()),
    )

    return document


async def delete_document(
    document_id: UUID,
    session: AsyncSession,
) -> None:
    """Delete a draft document.

    Only documents in draft status can be deleted. Active and archived
    documents have signing history or audit significance.

    Raises:
        NotFoundError: If document not found.
        BadRequestError: If document is not in draft status.
    """
    stmt = select(Document).where(Document.id == document_id)
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()

    if document is None:
        raise NotFoundError("Document not found")

    if document.status != DocumentStatus.DRAFT:
        raise BadRequestError(
            f"Only draft documents can be deleted (current: {document.status})"
        )

    await session.delete(document)
    await session.flush()

    logger.info(
        "document_deleted",
        document_id=str(document_id),
    )


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------


def _build_document_response(
    document: Document,
    is_signed: bool,
) -> DocumentResponse:
    """Build DocumentResponse with is_signed set at construction time."""
    return DocumentResponse(
        id=document.id,
        type=document.type,
        version=document.version,
        title=document.title,
        content_url=document.content_url,
        status=document.status,
        created_by=document.created_by,
        created_at=document.created_at,
        updated_at=document.updated_at,
        is_signed=is_signed,
    )


async def list_documents_for_role(
    role: str,
    user_id: UUID,
    session: AsyncSession,
) -> list[DocumentResponse]:
    """List active documents for a user's role with is_signed flag.

    Returns documents whose type is in ROLE_REQUIRED_DOCUMENT_TYPES
    for the given role, filtered to active status only.
    """
    doc_types = ROLE_REQUIRED_DOCUMENT_TYPES.get(role, [])
    if not doc_types:
        return []

    # Get active documents for the role.
    stmt = (
        select(Document)
        .where(
            Document.type.in_(doc_types),
            Document.status == DocumentStatus.ACTIVE,
        )
        .order_by(Document.type, Document.version.desc())
    )
    result = await session.execute(stmt)
    documents = result.scalars().all()

    if not documents:
        return []

    # Get user's signings for these documents in one query.
    doc_ids = [d.id for d in documents]
    signing_stmt = (
        select(DocumentSigning.document_id)
        .where(
            DocumentSigning.user_id == user_id,
            DocumentSigning.document_id.in_(doc_ids),
        )
    )
    signing_result = await session.execute(signing_stmt)
    signed_doc_ids = {row[0] for row in signing_result.all()}

    return [
        _build_document_response(doc, doc.id in signed_doc_ids)
        for doc in documents
    ]


async def get_document(
    document_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> DocumentResponse:
    """Get a single document with is_signed flag.

    Raises:
        NotFoundError: If document not found.
    """
    stmt = select(Document).where(Document.id == document_id)
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()

    if document is None:
        raise NotFoundError("Document not found")

    # Check if user signed this document.
    signing_stmt = (
        select(DocumentSigning)
        .where(
            DocumentSigning.user_id == user_id,
            DocumentSigning.document_id == document_id,
        )
    )
    signing_result = await session.execute(signing_stmt)
    signing = signing_result.scalar_one_or_none()

    return _build_document_response(document, signing is not None)


async def sign_document(
    user_id: UUID,
    document_id: UUID,
    ip_address: str,
    user_agent: str,
    session: AsyncSession,
) -> DocumentSigning:
    """Record user's checkbox consent for a document.

    Raises:
        NotFoundError: If document not found.
        BadRequestError: If document is not in active status.
        ConflictError: If user already signed this document.
    """
    # Load document.
    stmt = select(Document).where(Document.id == document_id)
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()

    if document is None:
        raise NotFoundError("Document not found")

    if document.status != DocumentStatus.ACTIVE:
        raise BadRequestError("Only active documents can be signed")

    # Truncate user_agent to prevent DoS.
    truncated_ua = user_agent[:USER_AGENT_MAX_LEN] if user_agent else ""

    signing = DocumentSigning(
        user_id=user_id,
        document_id=document_id,
        ip_address=ip_address,
        user_agent=truncated_ua,
    )
    session.add(signing)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_document_signings_user_document" in str(exc.orig):
            raise ConflictError("Document already signed")
        raise

    await session.refresh(signing)

    logger.info(
        "document_signed",
        user_id=str(user_id),
        document_id=str(document_id),
    )

    # Check if all required documents are now signed.
    await _maybe_complete_onboarding(user_id, session)

    return signing


# ---------------------------------------------------------------------------
# Onboarding completion check
# ---------------------------------------------------------------------------


async def _maybe_complete_onboarding(
    user_id: UUID,
    session: AsyncSession,
) -> None:
    """Advance onboarding to complete if all role docs are signed.

    Called after each document signing. Only acts when
    onboarding_step == kyc_done (the step right before completion).
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or user.onboarding_step != OnboardingStep.KYC_DONE:
        return

    # Get required doc types for this role.
    doc_types = ROLE_REQUIRED_DOCUMENT_TYPES.get(user.role, [])
    if not doc_types:
        # No docs required for this role — complete immediately.
        user.onboarding_step = OnboardingStep.ONBOARDING_COMPLETE
        await session.flush()
        logger.info("onboarding_complete", user_id=str(user_id))
        return

    # Active documents of required types.
    doc_stmt = (
        select(Document.id)
        .where(
            Document.type.in_(doc_types),
            Document.status == DocumentStatus.ACTIVE,
        )
    )
    doc_result = await session.execute(doc_stmt)
    active_doc_ids = {row[0] for row in doc_result.all()}

    if not active_doc_ids:
        return

    # User's signings for those documents.
    sign_stmt = (
        select(DocumentSigning.document_id)
        .where(
            DocumentSigning.user_id == user_id,
            DocumentSigning.document_id.in_(active_doc_ids),
        )
    )
    sign_result = await session.execute(sign_stmt)
    signed_ids = {row[0] for row in sign_result.all()}

    if active_doc_ids <= signed_ids:
        user.onboarding_step = OnboardingStep.ONBOARDING_COMPLETE
        await session.flush()
        logger.info("onboarding_complete", user_id=str(user_id))
