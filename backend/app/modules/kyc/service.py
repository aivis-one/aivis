# =============================================================================
# CBSHOME Backend -- KYC Service (Sprint 2.1)
# =============================================================================
#
# RESPONSIBILITIES:
#   submit_kyc()       -- create KYCApplication, sync User.kyc_status
#   get_kyc_status()   -- return current status + latest application
#   process_webhook()  -- update application + User.kyc_status (stub)
#
# SYNC RULE:
#   Every status change on KYCApplication MUST also update User.kyc_status.
#   User.kyc_status is a denormalized cache for fast eligibility checks.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.modules.kyc.models import KYCApplication, KYCApplicationStatus
from app.modules.kyc.schemas import KYCStatusResponse
from app.modules.users.models import User

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

    Creates a KYCApplication with status=submitted and syncs
    User.kyc_status to "submitted".

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
    user_id: str,
    new_status: str,
    session: AsyncSession,
) -> None:
    """Process KYC webhook -- update application and User.kyc_status.

    This is a stub: in production, SumSub signature validation
    will happen in the router before calling this function.

    Raises:
        BadRequestError: If new_status is not approved or rejected.
        NotFoundError: If user or pending application not found.
    """
    # Guard: validate status even though schema already checks.
    # Protects against internal callers bypassing schema validation.
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
