# =============================================================================
# CBSHOME Backend -- KYC Service (Sprint 2.1, F5.1 BP-15 follow-up)
# =============================================================================
#
# RESPONSIBILITIES:
#   submit_kyc()       -- create KYCApplication, sync User.kyc_status,
#                         advance onboarding_step immediately (non-blocking),
#                         and trigger maybe_complete_onboarding() so a role
#                         with zero required documents skips the docs page
#                         (BP-15).
#   get_kyc_status()   -- return current status + latest application
#   process_webhook()  -- update application + User.kyc_status (stub)
#
# NON-BLOCKING KYC:
#   submit_kyc() advances onboarding_step to KYC_DONE immediately.
#   User proceeds through onboarding while KYC verification runs
#   in background. Staff can approve/reject later without blocking
#   the user's ability to use the platform.
#
# BP-15 (no-docs auto-advance):
#   After moving to KYC_DONE, submit_kyc() calls
#   documents.service.maybe_complete_onboarding(). When the user's
#   role has no active required documents, that helper advances step
#   straight to ONBOARDING_COMPLETE -- previously the frontend's docs
#   page was reachable with an empty list and the user could not get
#   off it (sign_document() never fires, so the helper was never
#   invoked, so the step stayed on KYC_DONE forever). Symmetric with
#   the sign_document() callsite -- the helper is safe to call from
#   either path because of its own `step != KYC_DONE -> return` guard.
#
# SYNC RULE:
#   Every status change on KYCApplication MUST also update User.kyc_status.
#   User.kyc_status is a denormalized cache for fast eligibility checks.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.documents.service import maybe_complete_onboarding
from app.modules.kyc.models import KYCApplication, KYCApplicationStatus
from app.modules.kyc.schemas import KYCStatusResponse
from app.modules.users.models import OnboardingStep, User

logger = structlog.get_logger()

# Valid statuses accepted from webhook.
_VALID_WEBHOOK_STATUSES = {
    KYCApplicationStatus.APPROVED,
    KYCApplicationStatus.REJECTED,
}


async def submit_kyc(
    user: User,
    session: AsyncSession,
) -> KYCApplication:
    """Submit a new KYC application.

    Creates a KYCApplication with status=submitted, syncs
    User.kyc_status to "submitted", advances onboarding_step
    to KYC_DONE immediately (non-blocking KYC), and (BP-15)
    advances further to ONBOARDING_COMPLETE if the role has no
    required documents.

    Raises:
        ConflictError: If user already has a pending (submitted) application.
    """
    # Check for existing pending application.
    stmt = (
        select(KYCApplication)
        .where(
            KYCApplication.user_id == user.id,
            KYCApplication.status == KYCApplicationStatus.SUBMITTED,
        )
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise ConflictError("KYC application already submitted")

    # Create new application.
    application = KYCApplication(
        user_id=user.id,
        status=KYCApplicationStatus.SUBMITTED,
    )
    session.add(application)

    # Sync denormalized cache.
    old_status = user.kyc_status
    user.kyc_status = KYCApplicationStatus.SUBMITTED

    # Advance onboarding step immediately — KYC runs in background.
    if user.onboarding_step == OnboardingStep.ROLE_SELECTED:
        user.onboarding_step = OnboardingStep.KYC_DONE

    await session.flush()
    await session.refresh(application)

    # BP-15: if the role requires zero documents, auto-advance past
    # the docs page. The helper is a no-op when step != KYC_DONE
    # (e.g. user came in on a re-submit), so the unconditional call
    # is safe.
    await maybe_complete_onboarding(user.id, session)

    await session.refresh(user)

    await record_audit(
        session=session,
        event="kyc.status_changed",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={"from": old_status, "to": KYCApplicationStatus.SUBMITTED},
    )

    logger.info(
        "kyc_submitted",
        user_id=str(user.id),
        application_id=str(application.id),
    )

    return application


async def get_kyc_status(
    user: User,
    session: AsyncSession,
) -> KYCStatusResponse:
    """Return the current KYC status and latest application info."""
    # Get the most recent application.
    stmt = (
        select(KYCApplication)
        .where(KYCApplication.user_id == user.id)
        .order_by(KYCApplication.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    return KYCStatusResponse(
        kyc_status=user.kyc_status,
        application_id=application.id if application else None,
        application_status=application.status if application else None,
    )


async def process_webhook(
    user_id: UUID,
    new_status: str,
    session: AsyncSession,
) -> None:
    """Process KYC webhook -- update application and User.kyc_status.

    This is a stub: in production, SumSub signature validation
    will happen in the router before calling this function.

    Note: onboarding_step is NOT changed here because it was already
    advanced to KYC_DONE during submit (non-blocking KYC).

    Raises:
        BadRequestError: If new_status is not approved or rejected.
        NotFoundError: If user or pending application not found.
    """
    # Guard: validate status even though schema already checks.
    if new_status not in _VALID_WEBHOOK_STATUSES:
        raise BadRequestError(
            f"Invalid KYC status: {new_status}. "
            f"Valid: {', '.join(sorted(_VALID_WEBHOOK_STATUSES))}"
        )

    # Load user.
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise NotFoundError("User not found")

    # Find the latest submitted application.
    stmt = (
        select(KYCApplication)
        .where(
            KYCApplication.user_id == user.id,
            KYCApplication.status == KYCApplicationStatus.SUBMITTED,
        )
        .order_by(KYCApplication.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    if application is None:
        raise NotFoundError("No pending KYC application found")

    # Update application status.
    old_status = application.status
    application.status = new_status

    # Sync denormalized cache on User.
    user.kyc_status = new_status

    await session.flush()
    await session.refresh(user)

    await record_audit(
        session=session,
        event="kyc.status_changed",
        actor_id=None,
        actor_type="system",
        target_type="user",
        target_id=user.id,
        data={"from": old_status, "to": new_status},
    )

    logger.info(
        "kyc_webhook_processed",
        user_id=str(user.id),
        application_id=str(application.id),
        new_status=new_status,
    )
