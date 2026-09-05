# =============================================================================
# AIVIS.ONE Backend -- Admin Router (Sprint 3.3, G5 fix)
# =============================================================================
#
# ENDPOINTS:
#   GET  /api/v1/staff/dashboard/stats  -- platform statistics (any staff)
#   GET  /api/v1/staff/kyc/queue        -- pending KYC applications (kyc_approve)
#   POST /api/v1/staff/kyc/{id}/approve -- approve KYC (kyc_approve, reason required)
#   POST /api/v1/staff/kyc/{id}/reject  -- reject KYC (kyc_approve, reason required)
#   POST /api/v1/staff/kyc/users/{id}/approve -- approve a person with no
#                                        application (kyc_approve, reason required)
#   POST /api/v1/staff/kyc/users/{id}/revoke  -- withdraw an approval
#                                        (kyc_approve, reason required)
#   GET  /api/v1/staff/kyc/{id}/documents -- the images a session carries
#                                        (kyc_approve)
#   POST /api/v1/staff/kyc/documents/{id}/url -- a short-lived link to one
#                                        image (kyc_approve, audited)
#   GET  /api/v1/staff/kyc/verification-mode -- the platform switch (kyc_approve)
#   PUT  /api/v1/staff/kyc/verification-mode -- change it (kyc_approve)
#
# AUTH:
#   Dashboard: any staff (get_current_staff).
#   KYC: requires kyc_approve permission (require_staff_permission).
#
# ONE PERMISSION OVER THREE POWERS, and it is worth naming because it
# was not designed that way. kyc_approve gates deciding an application,
# reading the documents behind it, and moving the platform's
# verification mode. The first two the owner tied together on purpose
# -- approving without looking is what the documents exist to prevent.
# The third is attached rather than chosen: a settings permission of
# its own would be a new key in VALID_PERMISSION_KEYS, and every
# profile created before it existed would stop reading as admin (see
# migration 0043). It comes apart the day a second setting needs a
# different permission and a key -> permission map earns itself.
#
# THE PRESIGN ENDPOINT IS A POST, not a GET, because it WRITES: every
# call records who looked at whose passport. A GET that mutates would
# be re-fired by any retry, prefetch or refresh, and the audit log
# would fill with views that nobody performed.
#
# COMMIT RULE (P-01):
#   Routers never call session.commit(). get_db_session commits
#   automatically after yield.
# =============================================================================

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader, get_db_session
from app.modules.auth.dependencies import get_current_staff, require_staff_permission
from app.modules.kyc.constants import VerificationMode
from app.modules.kyc.schemas import (
    KYCDocumentResponse,
    KYCDocumentURLResponse,
    VerificationModeResponse,
    VerificationModeUpdate,
)
from app.modules.kyc.service import (
    get_verification_mode,
    issue_document_url,
    list_application_documents,
    set_verification_mode,
)
from app.modules.staff.admin_schemas import (
    DashboardStatsResponse,
    KYCDecisionRequest,
    KYCQueueItem,
)
from app.modules.staff.admin_service import (
    dashboard_stats,
    kyc_decide_application,
    kyc_decide_user,
    kyc_queue,
)
from app.modules.users.models import KYCStatus, User

logger = structlog.get_logger()

# Two sub-routers under /api/v1/staff.
dashboard_router = APIRouter(
    prefix="/api/v1/staff/dashboard",
    tags=["staff-dashboard"],
)
kyc_admin_router = APIRouter(
    prefix="/api/v1/staff/kyc",
    tags=["staff-kyc"],
)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@dashboard_router.get(
    "/stats",
    response_model=DashboardStatsResponse,
)
async def get_dashboard_stats(
    staff: User = Depends(get_current_staff),
    session: AsyncSession = Depends(get_db_reader),
) -> DashboardStatsResponse:
    """Platform-wide statistics. Any staff can view."""
    return await dashboard_stats(session)


# ---------------------------------------------------------------------------
# KYC queue
# ---------------------------------------------------------------------------


@kyc_admin_router.get(
    "/queue",
    response_model=list[KYCQueueItem],
)
async def get_kyc_queue(
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_reader),
) -> list[KYCQueueItem]:
    """List pending KYC applications. Requires kyc_approve permission."""
    return await kyc_queue(session)


@kyc_admin_router.post(
    "/{application_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def kyc_approve_endpoint(
    application_id: UUID,
    body: KYCDecisionRequest,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Approve a queued application. Requires kyc_approve permission."""
    await kyc_decide_application(
        application_id,
        KYCStatus.APPROVED,
        staff,
        session,
        reason=body.reason,
    )


@kyc_admin_router.post(
    "/{application_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def kyc_reject_endpoint(
    application_id: UUID,
    body: KYCDecisionRequest,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Reject a queued application. Requires kyc_approve permission."""
    await kyc_decide_application(
        application_id,
        KYCStatus.REJECTED,
        staff,
        session,
        reason=body.reason,
    )


@kyc_admin_router.post(
    "/users/{user_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def kyc_approve_user_endpoint(
    user_id: UUID,
    body: KYCDecisionRequest,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Approve a PERSON who has no queued application.

    Free, and routine rather than exceptional: this is how an old user
    arriving under a new address is let in, and how the seed script
    builds its users. They have no application to name, and cannot make
    one without paying.

    Three segments against the queue endpoint's two, so the two route
    templates cannot shadow each other.
    """
    await kyc_decide_user(
        user_id,
        KYCStatus.APPROVED,
        staff,
        session,
        reason=body.reason,
    )


@kyc_admin_router.post(
    "/users/{user_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def kyc_revoke_user_endpoint(
    user_id: UUID,
    body: KYCDecisionRequest,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Withdraw an approval, putting the person back behind the gate.

    Same permission as granting it, deliberately: a separate permission
    would create staff who can let somebody in and cannot take it back
    -- unable to correct their own mistake.
    """
    await kyc_decide_user(
        user_id,
        KYCStatus.REVOKED,
        staff,
        session,
        reason=body.reason,
    )


@kyc_admin_router.get(
    "/{application_id}/documents",
    response_model=list[KYCDocumentResponse],
)
async def kyc_application_documents_endpoint(
    application_id: UUID,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_reader),
) -> list[KYCDocumentResponse]:
    """List the images a verification session carries.

    AN EMPTY LIST IS AN ANSWER, NOT A 404. Applications created by the
    person-level approval path belong to somebody who never submitted
    anything, and answering 404 for them would tell staff the
    application does not exist when what is true is that it has no
    documents.

    No storage keys in the response: staff fetch each image through the
    presign endpoint below, which is where the read gets recorded.
    """
    documents = await list_application_documents(session, application_id)
    return [KYCDocumentResponse.model_validate(d) for d in documents]


@kyc_admin_router.post(
    "/documents/{document_id}/url",
    response_model=KYCDocumentURLResponse,
)
async def kyc_document_url_endpoint(
    document_id: UUID,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> KYCDocumentURLResponse:
    """Hand out a short-lived link to one identity document.

    Writes an audit row naming the staff member, the person the
    document belongs to, and the object key -- which is why this is a
    write session and a POST. Answers 404 when the row is unknown or
    the object behind it is gone from storage, rather than signing a
    link that fails at MinIO.
    """
    url, ttl_seconds = await issue_document_url(
        session,
        document_id=document_id,
        actor_id=staff.id,
    )
    return KYCDocumentURLResponse(url=url, ttl_seconds=ttl_seconds)


# ---------------------------------------------------------------------------
# The verification mode
# ---------------------------------------------------------------------------
#
# ON THE EXISTING KYC ROUTER, not a router of its own. The setting is
# KYC's and it is gated by the KYC permission; a "staff settings"
# router would be a prefix built to hold one pair of endpoints, and the
# next setting will belong to some other module anyway.


@kyc_admin_router.get(
    "/verification-mode",
    response_model=VerificationModeResponse,
)
async def get_verification_mode_endpoint(
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_reader),
) -> VerificationModeResponse:
    """Read the platform's verification mode.

    Same permission as writing it. Reading is not itself sensitive, but
    the only screen that shows this value is the one that changes it,
    and a reader who cannot write would be looking at a control they
    cannot use.
    """
    mode = await get_verification_mode(session)
    return VerificationModeResponse(mode=VerificationMode(mode))


@kyc_admin_router.put(
    "/verification-mode",
    response_model=VerificationModeResponse,
)
async def set_verification_mode_endpoint(
    body: VerificationModeUpdate,
    staff: User = Depends(require_staff_permission("kyc_approve")),
    session: AsyncSession = Depends(get_db_session),
) -> VerificationModeResponse:
    """Change the platform's verification mode.

    Takes effect for the next submission, not for sessions already
    open: an application records the mode it was submitted under and is
    decided that way whatever happens to this setting afterwards.

    THE AUTOMATIC MODE HAS NO SECOND HALF YET. The provider integration
    is the next pass; until it lands, a session submitted under either
    value is decided by a human. The setting is stored and stamped onto
    the row from the day it ships so that the pass which adds the
    provider has nothing to backfill.
    """
    stored = await set_verification_mode(
        session,
        body.mode.value,
        actor_id=staff.id,
    )
    return VerificationModeResponse(mode=VerificationMode(stored))
