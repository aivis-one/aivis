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

from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID, uuid4

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
from app.core.storage import (
    StorageError,
    generate_presigned_url,
    object_exists,
    upload_object,
)
from app.modules.kyc.constants import (
    DOCUMENT_TYPES_REQUIRING_BACK,
    KYC_ALLOWED_MIME_TYPES,
    KYC_EXTENSION_MIME_TYPES,
    KYC_HEIC_EXTENSIONS,
    KYC_MAX_DOCUMENT_BYTES,
    KYC_PRESIGNED_URL_TTL_SECONDS,
    KYC_STORAGE_PREFIX,
    KYC_VERIFICATION_FEE_CENTS,
    KYCDocumentKind,
    KYCDocumentType,
    VerificationMode,
)
from app.modules.kyc.models import (
    KYC_SETTINGS_ID,
    KYCApplication,
    KYCDocument,
    KYCSettings,
)
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
    KYCStatus.APPROVED,
    KYCStatus.REJECTED,
    KYCStatus.REVOKED,
}

# Batch 3 (2026-08-27), the first aivis producer of notification_request --
# see comms-profile/types.yaml for the type registration this depends on.
# English only: no backend-authored user-facing text is localized today
# (core/email.py has no locale branching either), so this does not newly
# create a gap, it inherits one.
_KYC_DECISION_COPY = {
    KYCStatus.APPROVED: (
        "Identity verification approved",
        "Your identity verification has been approved. You now have "
        "full access to the platform.",
    ),
    KYCStatus.REJECTED: (
        "Identity verification not approved",
        "Your identity verification was not approved. You can start a "
        "new verification from your account.",
    ),
    KYCStatus.REVOKED: (
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
# Platform configuration -- who decides a verification
# ---------------------------------------------------------------------------
#
# TWO FUNCTIONS ON ONE ROW, in this module rather than a settings module
# of their own. The setting is KYC's, and a module built to hold one
# value is a generalisation for a class with one member: the second
# setting of some other module belongs in THAT module's table, not in a
# shared bucket everybody has to reach into.


async def get_verification_mode(session: AsyncSession) -> str:
    """The mode in force, or the default when nothing has been set.

    NO ROW IS THE NORMAL STATE, not an error: every box starts empty
    and stays that way until a staff member first moves the switch.
    Manual is the default because manual is what works -- an untouched
    switch must not put the product into the state whose other half has
    not shipped.
    """
    stmt = select(KYCSettings).where(KYCSettings.id == KYC_SETTINGS_ID)
    result = await session.execute(stmt)
    settings_row = result.scalar_one_or_none()

    if settings_row is None:
        return VerificationMode.MANUAL

    return settings_row.verification_mode


async def set_verification_mode(
    session: AsyncSession,
    mode: str,
    *,
    actor_id: UUID,
) -> str:
    """Write the mode, creating the single row if it is not there yet.

    AUDITS EVERY WRITE, INCLUDING ONE THAT CHANGES NOTHING. Writing only
    on change would leave the log unable to answer "did anybody touch
    this on the day it went wrong"; a staff member who opened the screen
    and pressed save is a fact, and from == to says exactly that.

    Takes effect for the next submission only. An application records
    the mode it was submitted under and is decided that way whatever
    happens to this row afterwards -- otherwise one click would change
    how every already-paid session is handled.
    """
    stmt = select(KYCSettings).where(KYCSettings.id == KYC_SETTINGS_ID)
    result = await session.execute(stmt)
    settings_row = result.scalar_one_or_none()

    if settings_row is None:
        old_mode = VerificationMode.MANUAL
        settings_row = KYCSettings(
            id=KYC_SETTINGS_ID,
            verification_mode=mode,
            updated_by_id=actor_id,
        )
        session.add(settings_row)
    else:
        old_mode = settings_row.verification_mode
        settings_row.verification_mode = mode
        settings_row.updated_by_id = actor_id

    await session.flush()

    await record_audit(
        session=session,
        event="kyc.verification_mode_changed",
        actor_id=actor_id,
        actor_type="staff",
        target_type="kyc_settings",
        target_id=settings_row.id,
        data={"from": old_mode, "to": mode},
    )

    logger.info(
        "kyc_verification_mode_changed",
        from_mode=old_mode,
        to_mode=mode,
        actor_id=str(actor_id),
    )

    return settings_row.verification_mode


# ---------------------------------------------------------------------------
# Documents -- validation, naming, storage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingDocument:
    """One validated file on its way to storage.

    Built by the router from an UploadFile and handed to submit_kyc.
    The service takes this rather than UploadFile so that everything it
    needs is already resolved -- a stream, its length, and a MIME type
    that came from validation rather than from the client's header.
    """

    kind: str
    stream: BinaryIO
    size_bytes: int
    content_type: str


def validate_document_filename(filename: str, *, kind: str) -> str:
    """Resolve a MIME type from the filename's extension, or refuse.

    EXTENSION, NOT THE MULTIPART CONTENT-TYPE HEADER, for the reason
    companies/service.py's validate_attachment_mime_by_filename gives:
    the header is client-controlled and trivially spoofed, while the
    extension is what the browser fills in from the OS mapping.

    HEIC is refused BY NAME rather than as an unknown extension. An
    iPhone owner picking a photo out of the Files app sends one
    routinely, and "unsupported file type" tells them nothing they can
    act on; "convert to JPEG or PNG" does.

    Raises:
        BadRequestError: no filename, no extension, HEIC, or an
            extension outside the whitelist.
    """
    if not filename or "." not in filename:
        raise BadRequestError(
            f"The {kind} image needs a filename with an extension "
            f"(.jpg, .jpeg or .png).",
            code="kyc_document_no_extension",
        )

    extension = filename.rsplit(".", 1)[1].strip().lower()

    if extension in KYC_HEIC_EXTENSIONS:
        raise BadRequestError(
            "HEIC images are not accepted. Re-save the photo as JPEG "
            "or PNG and upload it again.",
            code="kyc_document_heic",
        )

    mime = KYC_EXTENSION_MIME_TYPES.get(extension)
    if mime is None or mime not in KYC_ALLOWED_MIME_TYPES:
        allowed = ", ".join(sorted(KYC_EXTENSION_MIME_TYPES))
        raise BadRequestError(
            f"The {kind} image must be one of: {allowed}.",
            code="kyc_document_type_not_allowed",
        )

    return mime


def validate_document_size(size_bytes: int, *, kind: str) -> None:
    """Refuse an empty file and one over the cap.

    BOTH ENDS, and the zero end is not theoretical: a form submitted
    with a file input that was opened and cancelled arrives as a part
    with a name and no bytes, and an empty object in the passport
    prefix is a row claiming a document that is not there.

    Raises:
        BadRequestError: zero bytes, or above KYC_MAX_DOCUMENT_BYTES.
    """
    if size_bytes <= 0:
        raise BadRequestError(
            f"The {kind} image is empty.",
            code="kyc_document_empty",
        )

    if size_bytes > KYC_MAX_DOCUMENT_BYTES:
        limit_mb = KYC_MAX_DOCUMENT_BYTES // (1024 * 1024)
        raise BadRequestError(
            f"The {kind} image is larger than {limit_mb} MB.",
            code="kyc_document_too_large",
        )


def required_document_kinds(document_type: str) -> tuple[str, ...]:
    """Which faces a submission of this document type must carry.

    The selfie is required in every case: without it a decision can
    confirm that the document is genuine but not that it belongs to the
    person holding the account, and a manual decision is the only kind
    this pass makes.
    """
    kinds = [KYCDocumentKind.FRONT, KYCDocumentKind.SELFIE]
    if document_type in DOCUMENT_TYPES_REQUIRING_BACK:
        kinds.insert(1, KYCDocumentKind.BACK)
    return tuple(kinds)


def build_document_storage_key(
    application_id: UUID,
    document_id: UUID,
    content_type: str,
) -> str:
    """Build the MinIO key for one identity document.

    NOTHING THE UPLOADER CONTROLS APPEARS IN THE KEY. Company
    attachments end their key with the (sanitised) original filename;
    that is right for a deck and wrong here, because a passport scan is
    routinely named after the person, the key travels into presigned
    URLs and into every audit row recording who looked, and a name is
    not needed to find the object. Dropping it also removes the entire
    sanitisation problem rather than solving it again.

    Both path segments are version-4 UUIDs, so one person's key gives
    no purchase on another's. The extension comes from the VALIDATED
    MIME type, never from the upload's own name.
    """
    extension = KYC_ALLOWED_MIME_TYPES[content_type]
    return f"{KYC_STORAGE_PREFIX}/{application_id}/{document_id}.{extension}"


async def list_application_documents(
    session: AsyncSession,
    application_id: UUID,
) -> list[KYCDocument]:
    """Documents attached to one application, oldest first.

    An empty list is a legitimate answer, not a 404: applications
    created by decide_by_user() for a person approved by hand have no
    documents and never will.
    """
    stmt = (
        select(KYCDocument)
        .where(KYCDocument.application_id == application_id)
        .order_by(KYCDocument.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def issue_document_url(
    session: AsyncSession,
    *,
    document_id: UUID,
    actor_id: UUID,
) -> tuple[str, int]:
    """Presign one document for viewing and record that it happened.

    THE AUDIT ROW IS THE POINT, not a side effect. Decisions were
    audited before this pass and reads were not, and with documents
    kept forever the question that gets asked after something happens
    is "who looked at this person's passport". The row carries the
    staff member, the user the document belongs to, and the object key
    -- the key because "a document" is not an answer when an
    application holds three.

    THE OBJECT IS CHECKED BEFORE THE URL IS SIGNED. Presigning is a
    local computation: it succeeds against a key that does not exist
    and hands back a link that 404s at MinIO instead of here, which
    reads to staff as "the link is broken" rather than "the document is
    gone". It would also write an audit row claiming a view that could
    not happen.

    Returns:
        (url, ttl_seconds)

    Raises:
        NotFoundError: no such document row, or the object behind it is
            missing from storage.
    """
    stmt = select(KYCDocument).where(KYCDocument.id == document_id)
    result = await session.execute(stmt)
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFoundError("KYC document not found")

    # Belt against a row whose key never got written -- a presign on an
    # empty key would sign the bucket root.
    if not document.storage_key:
        raise NotFoundError("KYC document has no stored object")

    stmt = select(KYCApplication).where(
        KYCApplication.id == document.application_id
    )
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()
    if application is None:
        raise NotFoundError("KYC application not found")

    if not await object_exists(document.storage_key):
        raise NotFoundError("KYC document object is missing from storage")

    url = await generate_presigned_url(
        document.storage_key,
        KYC_PRESIGNED_URL_TTL_SECONDS,
    )

    await record_audit(
        session=session,
        event="kyc.document_viewed",
        actor_id=actor_id,
        actor_type="staff",
        target_type="user",
        target_id=application.user_id,
        data={
            "application_id": str(application.id),
            "document_id": str(document.id),
            "kind": document.kind,
            "storage_key": document.storage_key,
            "ttl_seconds": KYC_PRESIGNED_URL_TTL_SECONDS,
        },
    )

    logger.info(
        "kyc_document_url_issued",
        document_id=str(document.id),
        application_id=str(application.id),
        actor_id=str(actor_id),
        storage_key=document.storage_key,
    )

    return url, KYC_PRESIGNED_URL_TTL_SECONDS


# ---------------------------------------------------------------------------
# Submit -- the paid entry
# ---------------------------------------------------------------------------


async def submit_kyc(
    user: User,
    session: AsyncSession,
    *,
    document_type: str,
    documents: list[PendingDocument],
    verification_mode: str,
) -> KYCApplication:
    """Charge the verification fee and open a verification session.

    Order is deliberate, and H12 added a step to it. The advisory lock
    first, then the conflict check, then the balance check, then the
    documents are checked as a SET, then every write. Two concurrent
    submits serialise on the lock, so the second one sees the first
    one's debit and is refused instead of charging twice against the
    same ten dollars.

    NOTHING IS WRITTEN UNTIL THE FILES ARE KNOWN TO BE ACCEPTABLE. Each
    file was checked one at a time by the router as it arrived; this
    function checks the SET -- that the kinds present are exactly the
    kinds this document type requires. A refusal here leaves no
    application row, no ledger entry, no transaction row and no object:
    there is no partial charge and no orphaned upload to clean up.

    THE UPLOAD HAPPENS BEFORE THE COMMIT, not after. The caller commits
    this transaction; if a storage failure raises here the whole
    transaction rolls back and the person is not charged. The other
    ordering -- commit, then upload -- fails the other way round, and
    that failure is a session that took ten dollars and holds no
    documents, which no reader of the row can distinguish from a
    session whose documents were deleted. An object written for a
    transaction that then fails to commit is unreferenced, invisible to
    every read path, and costs storage; that is the cheaper of the two.

    THE MODE IS RECORDED, NOT ACTED ON. `verification_mode` is written
    to the row and nothing branches on it: the provider integration is
    the next pass, so a manual decision is the only decision there is.
    Recording it now means the rows this pass creates say truthfully
    how they were decided instead of being backfilled with a guess.

    Raises:
        ConflictError: a session is already open for this user.
        InsufficientBalanceError: balance below the fee.
        BadRequestError: the document set is wrong for this type.
        StorageError: an upload failed; nothing is committed.
    """
    if document_type not in set(KYCDocumentType):
        raise BadRequestError(
            f"Unknown identity document type: {document_type}.",
            code="kyc_document_type_unknown",
        )

    # THE SET, NOT THE FILES. Each file's own type and size were
    # refused at the door; what is left is whether the right faces are
    # present -- no missing selfie, no back of a passport, no second
    # front.
    expected = required_document_kinds(document_type)
    supplied = tuple(d.kind for d in documents)

    if len(set(supplied)) != len(supplied):
        raise BadRequestError(
            "Each image may be supplied once.",
            code="kyc_documents_duplicate_kind",
        )

    if set(supplied) != set(expected):
        raise BadRequestError(
            f"A {document_type} submission requires exactly: "
            f"{', '.join(expected)}.",
            code="kyc_documents_incomplete",
        )

    # Serialise this user's money operations against purchases and
    # tranche payments, which take the same lock on the same key.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": user.id.int & 0x7FFFFFFFFFFFFFFF},
    )

    stmt = select(KYCApplication).where(
        KYCApplication.user_id == user.id,
        KYCApplication.status == KYCStatus.SUBMITTED,
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
        status=KYCStatus.SUBMITTED,
        decision_mode=verification_mode,
        document_type=document_type,
    )
    session.add(application)
    await session.flush()
    await session.refresh(application)

    stored_keys: list[str] = []
    for pending in documents:
        document_id = uuid4()
        storage_key = build_document_storage_key(
            application.id,
            document_id,
            pending.content_type,
        )

        try:
            await upload_object(
                storage_key,
                pending.stream,
                pending.content_type,
                content_length=pending.size_bytes,
            )
        except StorageError:
            # Let it out. The transaction has not committed, so the
            # application row, the ledger entry and the transaction row
            # all disappear with it and the person keeps their money.
            # Objects already written for this attempt stay behind
            # unreferenced -- named here rather than swept, because a
            # sweep would be a second failure path to get right for an
            # object nothing can reach.
            logger.error(
                "kyc_document_upload_failed",
                application_id=str(application.id),
                kind=pending.kind,
                storage_key=storage_key,
                already_written=stored_keys,
            )
            raise

        stored_keys.append(storage_key)
        session.add(
            KYCDocument(
                id=document_id,
                application_id=application.id,
                kind=pending.kind,
                storage_key=storage_key,
                content_type=pending.content_type,
                size_bytes=pending.size_bytes,
            )
        )

    await session.flush()

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
            "document_type": document_type,
            "decision_mode": verification_mode,
            "document_count": len(documents),
        },
    )

    logger.info(
        "kyc_submitted",
        user_id=str(user.id),
        application_id=str(application.id),
        fee_cents=KYC_VERIFICATION_FEE_CENTS,
        document_type=document_type,
        decision_mode=verification_mode,
        document_count=len(documents),
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
        # The int() that stood here is gone with the defect it worked
        # around -- see get_active_balance's docstring (H12 P-46g).
        available_cents=balance["frozen"] + balance["confirmed"],
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

    if application.status != KYCStatus.SUBMITTED:
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
        KYCStatus.APPROVED,
        KYCStatus.REVOKED,
    }:
        raise BadRequestError(
            f"Invalid decision for a user-level KYC action: {new_status}. "
            f"Valid: {KYCStatus.APPROVED}, "
            f"{KYCStatus.REVOKED}"
        )
    reason = _clean_reason(reason)

    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")

    if (
        new_status == KYCStatus.APPROVED
        and user.kyc_status == KYCStatus.APPROVED
    ):
        raise ConflictError(
            "This user is already approved.",
            code="kyc_already_approved",
        )

    if (
        new_status == KYCStatus.REVOKED
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
