# =============================================================================
# CBSHOME Backend -- KYC Service (Sprint 2.1, F5.1 BP-15 follow-up,
#                                  iter 2.7 onboarding-advance hotfix)
# =============================================================================
#
# RESPONSIBILITIES:
#   submit_kyc()                    -- create KYCApplication, sync
#                                      User.kyc_status, advance
#                                      onboarding_step via the helper.
#   get_kyc_status()                -- return current status + latest
#                                      application.
#   process_webhook()               -- update pending application +
#                                      User.kyc_status (stub).
#   advance_onboarding_after_kyc()  -- idempotent step-advancement
#                                      helper (iter 2.7 hotfix).
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
# iter 2.7 ONBOARDING-ADVANCE HOTFIX:
#   The original submit_kyc() inlined `if step == ROLE_SELECTED:
#   step = KYC_DONE` after creating the application row. That works
#   on the happy path (first submit, no pending application) but
#   fails for a re-entry scenario:
#
#     User has kyc_status='approved' (webhook fired in the past) but
#     onboarding_step is still 'role_selected' (e.g. DB seed, or a
#     prior submit that crashed before the advancement landed).
#     Visiting /onboarding/kyc shows the "approved" branch with a
#     Continue button. Clicking Continue navigates to /, the
#     onboarding guard sees step=role_selected, redirects back to
#     /onboarding/kyc. Silent infinite loop -- safeNavigate's
#     no-throw contract on the frontend swallows the redirect,
#     leaving no console trace.
#
#   The fix extracts the advancement rule into a standalone helper
#   `advance_onboarding_after_kyc()` -- idempotent, callable from
#   any site where we want to ensure the user is past the KYC step
#   when their kyc_status indicates they have at least submitted
#   once. submit_kyc() delegates to it; the new endpoint
#   POST /api/v1/kyc/advance also delegates to it for the
#   re-entry case described above. Mirrors documents.service's
#   maybe_complete_onboarding() shape -- single source of truth for
#   one advancement rule, multiple callsites.
#
#   process_webhook() is intentionally NOT modified: the webhook
#   arrives after submit_kyc() has already advanced the user, so
#   step is already past ROLE_SELECTED in the normal flow. Adding
#   the call there would be a no-op in practice and would broaden
#   the test blast radius for no gain.
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


# ---------------------------------------------------------------------------
# Onboarding step advancement (iter 2.7 hotfix)
# ---------------------------------------------------------------------------


async def advance_onboarding_after_kyc(
    user: User,
    session: AsyncSession,
) -> None:
    """Advance onboarding past the KYC step if the user is stuck on it.

    Idempotent. Safe to call from any site that wants to ensure the
    user is past the KYC step when their kyc_status indicates a
    submission has happened at least once.

    Rules:
      * No-op if onboarding_step is not ROLE_SELECTED -- the user is
        either still earlier in the flow (we have no business
        advancing them) or already past KYC (no work to do).
      * No-op if kyc_status is NOT_STARTED -- there is no submission
        to base the advancement on. Calling this before a real
        submit_kyc() would be a programming error elsewhere.
      * Otherwise: ROLE_SELECTED -> KYC_DONE, then delegate to
        maybe_complete_onboarding() which may cascade to
        ONBOARDING_COMPLETE for roles with zero required documents
        (BP-15 contract).

    Mirrors documents.service.maybe_complete_onboarding() in shape --
    single source of truth for one advancement rule, idempotent,
    safe to call repeatedly.

    The caller is responsible for ensuring `user` is attached to
    `session`. A `session.refresh(user)` at the end reloads any
    state changed by maybe_complete_onboarding().
    """
    if user.onboarding_step != OnboardingStep.ROLE_SELECTED:
        return
    if user.kyc_status == KYCApplicationStatus.NOT_STARTED:
        return

    user.onboarding_step = OnboardingStep.KYC_DONE
    await session.flush()

    # Cascade: a role with zero required documents jumps straight to
    # ONBOARDING_COMPLETE. The helper is safe no-op when step is not
    # exactly KYC_DONE.
    await maybe_complete_onboarding(user.id, session)
    await session.refresh(user)

    logger.info(
        "onboarding_advanced_after_kyc",
        user_id=str(user.id),
        to_step=user.onboarding_step,
    )


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


async def submit_kyc(
    user: User,
    session: AsyncSession,
) -> KYCApplication:
    """Submit a new KYC application.

    Creates a KYCApplication with status=submitted, syncs
    User.kyc_status to "submitted", and advances onboarding_step
    via advance_onboarding_after_kyc() (which moves ROLE_SELECTED
    to KYC_DONE and may cascade to ONBOARDING_COMPLETE per BP-15
    for roles with zero required documents).

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

    await session.flush()
    await session.refresh(application)

    # Advance onboarding step via the idempotent helper. It checks
    # both step and kyc_status before doing anything, so calling it
    # unconditionally here is safe -- the flush above guarantees it
    # sees user.kyc_status=SUBMITTED.
    await advance_onboarding_after_kyc(user, session)

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


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


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
