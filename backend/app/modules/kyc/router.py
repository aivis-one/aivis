# =============================================================================
# AIVIS.ONE Backend -- KYC Router (Sprint 2.1, H10)
# =============================================================================
#
# ENDPOINTS:
#   POST /api/v1/kyc/submit   -- multipart: the identity documents, the
#                                fee, and a verification session
#                                (auth required)
#   GET  /api/v1/kyc/status   -- current status, fee, and balance
#                                (auth required)
#
# SUBMIT IS MULTIPART SINCE H12 AND NO LONGER TAKES AN EMPTY BODY. Until
# this pass the endpoint charged ten dollars and opened a session
# carrying nothing, and staff approved without seeing anything. A
# request with no files is refused before the money is touched.
#
# THE FILES ARE STREAMED, NOT READ INTO MEMORY. UploadFile.file is
# handed straight to the storage layer with an explicit content length,
# the same shape companies/attachments_company_router.py uses -- the
# size comes from a seek, not from reading the body.
#
# BOTH ARE IN FRONT OF THE KYC GATE (kyc/gate.py's exempt list). A gate
# standing in front of the only door through it would lock every new
# investor out of the product permanently -- the same self-lock that
# put the deposit endpoints on that list.
#
# WHAT IS GONE, AND IT IS NOT COMING BACK IN THIS SHAPE (H10 P-44):
#   POST /webhook  -- the stub provider receiver. It authenticated by
#                     comparing a shared secret with hmac.compare_digest
#                     and no emptiness check, against a setting that
#                     defaulted to the empty string: with the secret
#                     unset and the header absent, the comparison was
#                     "" against "", which is True, and the request
#                     then approved whatever user id its body named.
#                     Removed rather than repaired -- the verification
#                     provider that replaces it signs its callbacks.
#   POST /advance  -- an onboarding-unstick hotfix for a step that no
#                     longer exists.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
#
# SESSION NOTE:
#   GET /status uses get_current_user (read session) + get_db_reader.
#   FastAPI caches Depends within a request, so both share the same
#   read-only session instance.
# =============================================================================

import structlog
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.avatar_guard import forbid_avatar
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.kyc.constants import KYCDocumentKind, KYCDocumentType
from app.modules.kyc.schemas import KYCStatusResponse, KYCSubmitResponse
from app.modules.kyc.service import (
    PendingDocument,
    get_kyc_status,
    get_verification_mode,
    submit_kyc,
    validate_document_filename,
    validate_document_size,
)
from app.modules.users.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/kyc", tags=["kyc"])


def _resolve_upload_size(file: UploadFile) -> int:
    """Return the upload's size without reading the body into memory.

    Same helper, by name and by shape, as the one in
    companies/attachments_company_router.py and
    roadmap_company_router.py -- each router keeps its own copy by
    existing project convention rather than importing a private helper
    across router modules.
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


def _prepare(file: UploadFile, kind: str) -> PendingDocument:
    """Validate one uploaded part and describe it for the service.

    Type first, then size. A twenty-megabyte HEIC should be told it is
    a HEIC -- refusing it for its size would send the person off to
    compress a file we were never going to accept in any size.
    """
    content_type = validate_document_filename(file.filename or "", kind=kind)
    size_bytes = _resolve_upload_size(file)
    validate_document_size(size_bytes, kind=kind)
    return PendingDocument(
        kind=kind,
        stream=file.file,
        size_bytes=size_bytes,
        content_type=content_type,
    )


@router.post(
    "/submit",
    response_model=KYCSubmitResponse,
    status_code=status.HTTP_201_CREATED,
    # R49: staff in avatar mode must not submit KYC for the user. The
    # guard matters more since H10 than it did before: submitting now
    # spends the user's money, and since H12 it also stores the user's
    # identity documents.
    dependencies=[Depends(forbid_avatar("modify_kyc"))],
)
async def kyc_submit(
    document_type: KYCDocumentType = Form(...),
    front_image: UploadFile = File(...),
    selfie_image: UploadFile = File(...),
    back_image: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user_write),
    session: AsyncSession = Depends(get_db_session),
) -> KYCSubmitResponse:
    """Upload the identity documents and open a paid verification session.

    402 from the gate means "not verified"; this endpoint answers 400
    with insufficient_balance when the account cannot cover the fee,
    400 with a kyc_document_* code when a file is unacceptable, and 409
    when a session is already open and awaiting a decision.

    FRONT AND SELFIE ARE REQUIRED BY THE SIGNATURE, BACK IS NOT, and
    that asymmetry is the truth about the document types: a passport
    has one identity page, an ID card and a driving licence carry half
    their data on the reverse. Which of the three a given submission
    needs is decided in the service against document_type -- declaring
    back_image required here would make a passport submission
    impossible, and declaring all three optional would move the whole
    rule into prose.

    THE MODE IS READ HERE AND ONLY RECORDED. Until the provider pass
    lands there is one decision path -- a human -- so the value is
    written onto the row and nothing branches on it. Reading it at
    submit time rather than at decision time is what stops a staff
    member moving the switch and changing how sessions that were
    already paid for get handled.
    """
    documents = [
        _prepare(front_image, KYCDocumentKind.FRONT),
        _prepare(selfie_image, KYCDocumentKind.SELFIE),
    ]
    if back_image is not None and back_image.filename:
        documents.append(_prepare(back_image, KYCDocumentKind.BACK))

    verification_mode = await get_verification_mode(session)

    application = await submit_kyc(
        user,
        session,
        document_type=document_type,
        documents=documents,
        verification_mode=verification_mode,
    )
    return KYCSubmitResponse.model_validate(application)


@router.get(
    "/status",
    response_model=KYCStatusResponse,
)
async def kyc_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_reader),
) -> KYCStatusResponse:
    """Current KYC status, what a session costs, and what is available.

    get_current_user and get_db_reader share the same read-only session
    (FastAPI Depends caching within a request).
    """
    return await get_kyc_status(user, session)
