# =============================================================================
# AIVIS.ONE Backend -- Document Service (Sprint 2.2, updated by 0024, 0025)
# =============================================================================
#
# RESPONSIBILITIES:
#   Staff operations:
#     create_document()  -- create new document in draft status
#     update_document()  -- update document fields + status transitions
#     delete_document()  -- delete draft documents only
#
#   User operations:
#     list_documents_for_role()  -- active docs for role, in user's locale
#                                   (fallback to 'en'); raises if a required
#                                   type has no active row in either locale
#     get_document()             -- single document with is_signed flag
#     sign_document()            -- record checkbox consent
#
#   Cross-module:
#     maybe_complete_onboarding() -- BP-15 step advance helper. Public so
#                                    submit_kyc() can call it for the
#                                    no-documents-required edge case.
#
# STATUS TRANSITIONS (State Machines v1.4 section 5):
#     draft  -> active    (Staff: publish)
#     active -> draft     (Staff: unpublish for edits)
#     active -> archived  (Staff: archive)
#     draft  -> archived  (Staff: cancel draft)
#
# ROLE MAPPING (0024):
#   Document.required_for_roles is a JSONB array of role names. Role
#   filtering uses PostgreSQL JSONB containment via
#   SQLAlchemy's `.contains([role])`.
#
# LOCALISATION (0025):
#   Each active document row belongs to one locale. For listing we pick
#   the user's locale per type, falling back to 'en' if the locale copy
#   is missing. The user signs the exact row they read, so the signing
#   language is recorded via DocumentSigning.document_id.
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
from app.modules.documents.constants import VALID_STATUS_TRANSITIONS
from app.modules.documents.models import (
    Document,
    DocumentSigning,
    DocumentStatus,
)
from app.modules.documents.schemas import (
    DocumentCreateRequest,
    DocumentResponse,
    DocumentUpdateRequest,
)
from app.modules.users.models import OnboardingStep, User

logger = structlog.get_logger()

# English is the guaranteed baseline language -- every document type
# MUST have an active English row. When a user's locale copy is
# missing we fall back to this.
FALLBACK_LANGUAGE = "en"


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
        ConflictError: If (type, version, language) combination already exists.
    """
    document = Document(
        type=body.type,
        version=body.version,
        language=body.language,
        title=body.title,
        required_for_roles=list(body.required_for_roles),
        status=DocumentStatus.DRAFT,
        created_by=staff_id,
    )
    session.add(document)

    try:
        await session.flush()
    except IntegrityError as exc:
        if "uq_documents_type_version_language" in str(exc.orig):
            raise ConflictError(
                f"Document {body.type} v{body.version} "
                f"[{body.language}] already exists"
            )
        raise

    await session.refresh(document)

    logger.info(
        "document_created",
        document_id=str(document.id),
        type=document.type,
        language=document.language,
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
    if (
        "required_for_roles" in updates
        and updates["required_for_roles"] is not None
    ):
        # JSONB mutation must go through set_jsonb to flag the column dirty.
        document.set_jsonb(
            "required_for_roles", list(updates["required_for_roles"])
        )

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
        language=document.language,
        title=document.title,
        required_for_roles=list(document.required_for_roles or []),
        status=document.status,
        created_by=document.created_by,
        created_at=document.created_at,
        updated_at=document.updated_at,
        is_signed=is_signed,
    )


async def list_documents_for_role(
    role: str,
    user_language: str,
    user_id: UUID,
    session: AsyncSession,
) -> list[DocumentResponse]:
    """Active documents required for the role, in the user's locale.

    For each required type we return one row:
      - the document in `user_language` if available,
      - otherwise the `en` fallback,
      - otherwise raise -- the platform is misconfigured (seed bug
        or missing HTML file). The user must not proceed until an
        admin fixes the legal folder.

    Raises:
        RuntimeError: a required document type has no active row in the
            user's locale and no English fallback.
    """
    # Collect every active row for the role, but only in the two
    # languages that can possibly be returned: the user's and 'en'.
    candidate_langs = [user_language]
    if user_language != FALLBACK_LANGUAGE:
        candidate_langs.append(FALLBACK_LANGUAGE)

    stmt = (
        select(Document)
        .where(
            Document.status == DocumentStatus.ACTIVE,
            Document.required_for_roles.contains([role]),
            Document.language.in_(candidate_langs),
        )
        .order_by(Document.type, Document.version.desc())
    )
    result = await session.execute(stmt)
    candidates = result.scalars().all()

    # Independently list every active type required for this role,
    # across all languages -- this tells us which types MUST be
    # resolvable for the user.
    types_stmt = (
        select(Document.type)
        .where(
            Document.status == DocumentStatus.ACTIVE,
            Document.required_for_roles.contains([role]),
        )
        .distinct()
    )
    types_result = await session.execute(types_stmt)
    required_types: set[str] = {row[0] for row in types_result.all()}

    if not required_types:
        return []

    # Pick the best row per type: user_language > en.
    chosen: dict[str, Document] = {}
    for doc in candidates:
        current = chosen.get(doc.type)
        if current is None:
            chosen[doc.type] = doc
            continue
        # Prefer the user's own language over the fallback.
        if (
            doc.language == user_language
            and current.language != user_language
        ):
            chosen[doc.type] = doc

    missing = required_types - set(chosen.keys())
    if missing:
        # Admin misconfiguration -- a required type has no row in either
        # the user's locale or in English. Surface as a 500 so the
        # person responsible sees it immediately; onboarding halts.
        logger.error(
            "legal_documents_misconfigured",
            role=role,
            user_language=user_language,
            missing_types=sorted(missing),
        )
        raise RuntimeError(
            "Legal documents misconfigured: no active row "
            f"for types {sorted(missing)} in language "
            f"{user_language!r} or {FALLBACK_LANGUAGE!r}."
        )

    selected_docs = list(chosen.values())

    # Fetch user's signings for those documents in one go.
    doc_ids = [d.id for d in selected_docs]
    signing_stmt = (
        select(DocumentSigning.document_id)
        .where(
            DocumentSigning.user_id == user_id,
            DocumentSigning.document_id.in_(doc_ids),
        )
    )
    signing_result = await session.execute(signing_stmt)
    signed_doc_ids = {row[0] for row in signing_result.all()}

    # Return in a stable order: by type, then by language for determinism.
    selected_docs.sort(key=lambda d: (d.type, d.language))
    return [
        _build_document_response(doc, doc.id in signed_doc_ids)
        for doc in selected_docs
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
    await maybe_complete_onboarding(user_id, session)

    return signing


# ---------------------------------------------------------------------------
# Onboarding completion check
# ---------------------------------------------------------------------------


async def maybe_complete_onboarding(
    user_id: UUID,
    session: AsyncSession,
) -> None:
    """Advance onboarding to complete if the user signed every required type.

    Two callers cover BP-15 ("Auto-advance при 0 элементов"):
      - sign_document() in this module: fires after every successful
        signing; advances when the last required type gets signed.
      - select_role() in users/service.py: fires right after step is
        moved to ROLE_SELECTED; advances immediately if the user's
        role has zero required documents (otherwise stays on
        ROLE_SELECTED so the frontend can render the docs list).

    ANCHORED ON ROLE_SELECTED SINCE H10, not on KYC_DONE. Verification
    is no longer an onboarding step, so the step that used to sit
    between role and documents is gone; ROLE_SELECTED now means exactly
    what KYC_DONE meant here -- role chosen, documents outstanding.
    Left anchored on the removed step, this helper would never fire and
    every user would sit on the role page for good.

    Public (no leading underscore) because select_role imports it
    cross-module. The internal guard `step != ROLE_SELECTED -> return`
    keeps the function safe to call from any callsite without
    pre-check ceremony.

    Group-by `type`, not document id: a user who signed the English
    Privacy Policy in one session and (after a locale switch) the
    Russian one in another session is still considered done on the
    `privacy_policy` type.
    """
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or user.onboarding_step != OnboardingStep.ROLE_SELECTED:
        return

    # Every active doc row required for the user's role, across all
    # languages. Map id -> type for quick lookup.
    doc_stmt = (
        select(Document.id, Document.type)
        .where(
            Document.status == DocumentStatus.ACTIVE,
            Document.required_for_roles.contains([user.role]),
        )
    )
    doc_result = await session.execute(doc_stmt)
    rows = doc_result.all()

    if not rows:
        # No docs required for this role -- nothing left to sign.
        user.onboarding_step = OnboardingStep.ONBOARDING_COMPLETE
        await session.flush()
        logger.info("onboarding_complete", user_id=str(user_id))
        return

    id_to_type = {row[0]: row[1] for row in rows}
    required_types = set(id_to_type.values())

    sign_stmt = (
        select(DocumentSigning.document_id)
        .where(
            DocumentSigning.user_id == user_id,
            DocumentSigning.document_id.in_(id_to_type.keys()),
        )
    )
    sign_result = await session.execute(sign_stmt)
    signed_types = {
        id_to_type[row[0]]
        for row in sign_result.all()
        if row[0] in id_to_type
    }

    if required_types <= signed_types:
        user.onboarding_step = OnboardingStep.ONBOARDING_COMPLETE
        await session.flush()
        logger.info("onboarding_complete", user_id=str(user_id))
