# =============================================================================
# AIVIS.ONE Backend -- KYC Service (Sprint 2.1, H10 paid gate + manual decision)
# =============================================================================
#
# RESPONSIBILITIES:
#   submit_kyc()            -- charge the verification fee, open a
#                              verification session (KYCApplication),
#                              sync User.kyc_status.
#   get_kyc_status()        -- current status, latest application, and
#                              what a session costs against what the
#                              account holds.
#   decide_by_application() -- staff decision on a queued application.
#   decide_by_user()        -- staff decision on a PERSON, creating the
#                              application row when there is none.
#
# H10 -- WHAT CHANGED AND WHY IT READS DIFFERENTLY FROM THE OLD FILE:
#
#   THE FEE IS TAKEN BEFORE VERIFICATION, NOT AFTER. Charging on success
#   would make a flood of junk submissions free. The money is spent when
#   the session opens and is not returned by any outcome -- there is no
#   refund path in this module because there is no refund.
#
#   THE FEE BUYS A SESSION, NOT AN ATTEMPT. While an application sits in
#   SUBMITTED the person may come and go; a second submit is refused
#   with a conflict rather than charged again. Only a session that
#   reached a terminal decision requires a new one.
#
#   THERE IS NO WEBHOOK ANY MORE. process_webhook() was the stub
#   provider receiver; it and its endpoint are gone (H10 P-44), with the
#   shared-secret comparison that accepted an empty secret against an
#   empty header. What survived is the part that was never about
#   webhooks -- writing a decision -- under a name that says so.
#   Automatic verification returns in the Didit pass; until then the
#   only route to APPROVED is a staff decision.
#
#   KYC IS NO LONGER AN ONBOARDING STEP. advance_onboarding_after_kyc()
#   and POST /kyc/advance existed to move users past OnboardingStep
#   .KYC_DONE, and that step no longer exists. Onboarding is now
#   role -> documents, and documents.maybe_complete_onboarding() is
#   anchored on ROLE_SELECTED.
#
# SYNC RULE:
#   Every status change on KYCApplication MUST also update
#   User.kyc_status -- the denormalised cache the gate reads on every
#   request.
#
# REASONS LIVE IN THE AUDIT LOG, NOT ON THE MODEL. One fact, one place:
#   a decision_reason column beside the audit row would be a second copy,
#   and the first person to correct one would leave the other lying.
#
# COMMIT RULE (P-01):
#   Service never commits. Caller (get_db_session) manages the transaction.
# =============================================================================

from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.comms import comms_configured
from app.core.constants import LedgerReason
from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    InsufficientBalanceError,
    NotFoundError,
)
from app.modules.kyc.constants import KYC_VERIFICATION_FEE_CENTS
from app.modules.kyc.models import KYCApplication, KYCApplicationStatus
from app.modules.kyc.schemas import KYCStatusResponse
from app.modules.ledgers.models import LedgerStatus
from app.modules.ledgers.service import get_active_balance, record_active_ledger
from app.modules.transactions.constants import ReferenceType, TransactionType
from app.modules.transactions.service import record_transaction
from app.modules.users.models import KYCStatus, User

logger = structlog.get_logger()

# Statuses a decision may write. NOT_STARTED and SUBMITTED are absent on
# purpose: neither is a decision, and a "decision" that moved somebody
# back to SUBMITTED would leave a paid session indistinguishable from an
# unpaid one.
_DECISION_STATUSES = {
    KYCApplicationStatus.APPROVED,
    KYCApplicationStatus.REJECTED,
    KYCApplicationStatus.REVOKED,
}

# Batch 3 (2026-08-27), the first aivis producer of notification_request --
# see comms-profile/types.yaml for the type registration this depends on.
# English only: no backend-authored user-facing text is localized today
# (core/email.py has no locale branching either), so this does not newly
# create a gap, it inherits one.
_KYC_DECISION_COPY = {
    KYCApplicationStatus.APPROVED: (
        "Identity verification approved",
        "Your identity verification has been approved. You now have "
        "full access to the platform.",
    ),
    KYCApplicationStatus.REJECTED: (
        "Identity verification not approved",
        "Your identity verification was not approved. You can start a "
        "new verification from your account.",
    ),
    KYCApplicationStatus.REVOKED: (
        "Identity verification withdrawn",
        "Your identity verification approval has been withdrawn. "
        "Contact support if you believe this is a mistake.",
    ),
}


def _clean_reason(reason: str) -> str:
    """Return the reason stripped, refusing anything that is only space.

    The schema already rejects a missing key and an empty string; this
    catches the third form -- whitespace -- and keeps the guarantee at
    the service, where seed scripts and future callers arrive without
    passing through a Pydantic model.
    """
    cleaned = reason.strip() if reason else ""
    if not cleaned:
        raise BadRequestError(
            "A reason is required for a KYC decision.",
            code="kyc_reason_required",
        )
    return cleaned


# ---------------------------------------------------------------------------
# Submit -- the paid entry
# ---------------------------------------------------------------------------


async def submit_kyc(
    user: User,
    session: AsyncSession,
) -> KYCApplication:
    """Charge the verification fee and open a verification session.

    Order is deliberate: the advisory lock first, then the balance
    check, then every write. Two concurrent submits serialise on the
    lock, so the second one sees the first one's debit and is refused
    instead of charging twice against the same ten dollars.

    Nothing is written before the balance check passes, and everything
    written afterwards belongs to one transaction the caller commits --
    so a refusal leaves no application row, no ledger entry and no
    transaction row. There is no partial charge to clean up.

    Raises:
        ConflictError: a session is already open for this user.
        InsufficientBalanceError: balance below the fee.
    """
    # Serialise this user's money operations against purchases and
    # tranche payments, which take the same lock on the same key.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": user.id.int & 0x7FFFFFFFFFFFFFFF},
    )

    stmt = select(KYCApplication).where(
        KYCApplication.user_id == user.id,
        KYCApplication.status == KYCApplicationStatus.SUBMITTED,
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise ConflictError(
            "A verification session is already open and awaiting a "
            "decision.",
            code="kyc_already_in_progress",
        )

    # Frozen counts, exactly as it does for a purchase: a deposit that
    # has not finished confirming is still this person's money, and the
    # two spending paths must not disagree about what a balance is.
    balance = await get_active_balance(session, user.id)
    available = balance["frozen"] + balance["confirmed"]
    if available < KYC_VERIFICATION_FEE_CENTS:
        raise InsufficientBalanceError(
            available=available,
            required=KYC_VERIFICATION_FEE_CENTS,
        )

    application = KYCApplication(
        user_id=user.id,
        status=KYCApplicationStatus.SUBMITTED,
    )
    session.add(application)
    await session.flush()
    await session.refresh(application)

    await record_active_ledger(
        session,
        user_id=user.id,
        amount_cents=-KYC_VERIFICATION_FEE_CENTS,
        status=LedgerStatus.CONFIRMED,
        reason=LedgerReason.KYC_VERIFICATION.format(
            application_id=str(application.id)
        ),
    )

    await record_transaction(
        session,
        user_id=user.id,
        type=TransactionType.KYC_VERIFICATION_FEE,
        amount_cents=-KYC_VERIFICATION_FEE_CENTS,
        reference_id=application.id,
        reference_type=ReferenceType.KYC_APPLICATION,
    )

    old_status = user.kyc_status
    user.kyc_status = KYCStatus.SUBMITTED
    await session.flush()

    await record_audit(
        session=session,
        event="kyc.status_changed",
        actor_id=user.id,
        actor_type="user",
        target_type="user",
        target_id=user.id,
        data={
            "from": old_status,
            "to": KYCStatus.SUBMITTED,
            "application_id": str(application.id),
            "fee_cents": KYC_VERIFICATION_FEE_CENTS,
        },
    )

    logger.info(
        "kyc_submitted",
        user_id=str(user.id),
        application_id=str(application.id),
        fee_cents=KYC_VERIFICATION_FEE_CENTS,
    )

    return application


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def get_kyc_status(
    user: User,
    session: AsyncSession,
) -> KYCStatusResponse:
    """Return the current KYC status, latest application, and the money.

    The two amounts are here because the screen that needs them cannot
    reach dashboard/summary: that endpoint is behind the gate, and this
    one is in front of it by design.
    """
    stmt = (
        select(KYCApplication)
        .where(KYCApplication.user_id == user.id)
        .order_by(KYCApplication.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    balance = await get_active_balance(session, user.id)

    return KYCStatusResponse(
        kyc_status=user.kyc_status,
        application_id=application.id if application else None,
        application_status=application.status if application else None,
        fee_cents=KYC_VERIFICATION_FEE_CENTS,
        # int() for the same reason as in gate.py: get_active_balance
        # is annotated int and hands back Decimal.
        available_cents=int(balance["frozen"]) + int(balance["confirmed"]),
    )


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


async def _write_decision(
    *,
    user: User,
    application: KYCApplication,
    new_status: str,
    reason: str,
    actor_id: UUID | None,
    session: AsyncSession,
) -> KYCApplication:
    """Apply a terminal decision to an application and its user.

    One audit row carries everything about the decision: who, on whom,
    from what to what, and why. The previous shape wrote two rows -- a
    "system" status change plus a staff-flavoured one -- and the reason
    lived on only one of them, so reading either row alone gave an
    incomplete account of the same event.
    """
    old_status = application.status
    application.status = new_status
    user.kyc_status = new_status

    await session.flush()
    await session.refresh(user)

    await record_audit(
        session=session,
        event="kyc.status_changed",
        actor_id=actor_id,
        actor_type="staff" if actor_id is not None else "system",
        target_type="user",
        target_id=user.id,
        data={
            "from": old_status,
            "to": new_status,
            "application_id": str(application.id),
            "reason": reason,
        },
    )

    if comms_configured():
        # Same gate as comms_sync.ensure_recipient / support.service's
        # emit_support_membership: without a comms address the relay is
        # disabled too (same empty setting), so a row emitted here would
        # sit in the outbox forever with nobody to ship it.
        title, body = _KYC_DECISION_COPY[new_status]
        await emit_event(
            session,
            EVENT_NOTIFICATION_REQUEST,
            {
                # An application receives at most one decision that
                # leaves SUBMITTED, but a revocation is a SECOND
                # decision on the same row -- so the key carries the
                # status as well. Keyed on the application alone, a
                # revocation would be silently deduplicated against the
                # approval it withdraws, and the person would never be
                # told.
                "idempotency_key": f"kyc-decision:{application.id}:{new_status}",
                "type": f"kyc.{new_status}",
                "target_type": "user",
                "target_value": str(user.id),
                "title": title,
                "body": body,
            },
        )

    logger.info(
        "kyc_decision_applied",
        user_id=str(user.id),
        application_id=str(application.id),
        from_status=old_status,
        to_status=new_status,
        actor_id=str(actor_id) if actor_id else None,
    )

    return application


async def decide_by_application(
    *,
    application_id: UUID,
    new_status: str,
    reason: str,
    actor_id: UUID,
    session: AsyncSession,
) -> KYCApplication:
    """Decide a queued application -- the staff queue's entry point.

    For the person who paid, submitted, and is waiting. The queue lists
    exactly the applications this accepts.

    Raises:
        BadRequestError: status is not a decision, or reason is blank.
        NotFoundError: no such application, or its user is gone.
        ConflictError: the application already has a decision.
    """
    if new_status not in _DECISION_STATUSES:
        raise BadRequestError(
            f"Invalid KYC decision: {new_status}. "
            f"Valid: {', '.join(sorted(_DECISION_STATUSES))}"
        )
    reason = _clean_reason(reason)

    stmt = select(KYCApplication).where(KYCApplication.id == application_id)
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()
    if application is None:
        raise NotFoundError("KYC application not found")

    if application.status != KYCApplicationStatus.SUBMITTED:
        raise ConflictError(
            f"This application already has a decision: "
            f"{application.status}.",
            code="kyc_already_decided",
        )

    stmt = select(User).where(User.id == application.user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")

    return await _write_decision(
        user=user,
        application=application,
        new_status=new_status,
        reason=reason,
        actor_id=actor_id,
        session=session,
    )


async def decide_by_user(
    *,
    user_id: UUID,
    new_status: str,
    reason: str,
    actor_id: UUID | None,
    session: AsyncSession,
) -> KYCApplication:
    """Decide about a PERSON, with or without an application on file.

    THE ENTRY POINT THE QUEUE CANNOT PROVIDE. Approving someone who
    never applied is a routine flow, not an emergency one: an old user
    arriving under a new address is approved by hand, and the seed
    script builds its users the same way. Such a person has no
    application, is in no queue, and has no application_id to name --
    and cannot get one without paying, while a manual approval is free.
    Without this function that flow is simply impossible.

    Accepts APPROVED and REVOKED. Rejection stays application-only: a
    refusal is a verdict on a submission, and there is nothing to refuse
    from somebody who never submitted.

    Creates the application row when none exists, already carrying the
    decision -- so user.kyc_status and the application history never
    disagree, including for an imported account approved before this
    table had a row for them.

    Raises:
        BadRequestError: status is not APPROVED or REVOKED, or reason is blank.
        NotFoundError: no such user.
        ConflictError: already approved, or revoking someone not approved.
    """
    if new_status not in {
        KYCApplicationStatus.APPROVED,
        KYCApplicationStatus.REVOKED,
    }:
        raise BadRequestError(
            f"Invalid decision for a user-level KYC action: {new_status}. "
            f"Valid: {KYCApplicationStatus.APPROVED}, "
            f"{KYCApplicationStatus.REVOKED}"
        )
    reason = _clean_reason(reason)

    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")

    if (
        new_status == KYCApplicationStatus.APPROVED
        and user.kyc_status == KYCStatus.APPROVED
    ):
        raise ConflictError(
            "This user is already approved.",
            code="kyc_already_approved",
        )

    if (
        new_status == KYCApplicationStatus.REVOKED
        and user.kyc_status != KYCStatus.APPROVED
    ):
        raise ConflictError(
            "Only an approved verification can be withdrawn.",
            code="kyc_not_approved",
        )

    stmt = (
        select(KYCApplication)
        .where(KYCApplication.user_id == user.id)
        .order_by(KYCApplication.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    if application is None:
        # No paid session to attach the decision to. The row is created
        # carrying the decision itself rather than passing through
        # SUBMITTED: passing through would make the history claim a fee
        # was charged, and this path is free.
        application = KYCApplication(user_id=user.id, status=new_status)
        session.add(application)
        await session.flush()
        await session.refresh(application)

    return await _write_decision(
        user=user,
        application=application,
        new_status=new_status,
        reason=reason,
        actor_id=actor_id,
        session=session,
    )
