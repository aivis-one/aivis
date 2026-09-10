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
#   with a conflict rather than charged again. A session that ended in
#   REJECTED or REVOKED is replaced by a new, paid one.
#
#   NARROWED IN H13 (P-52), AND THIS IS THE ONE PLACE THE FULL
#   STATEMENT LIVES. The paragraph above used to end "only a session
#   that reached a terminal decision requires a new one". APPROVED is a
#   terminal decision, so that sentence licensed exactly what
#   submit_kyc then did: it charged a verified person the fee a second
#   time, stored a second set of identity documents that this module
#   has no path to delete, and moved them back behind the gate until
#   staff decided again. What the old wording had right survives
#   untouched -- a decision is what closes a session, and a closed
#   session is never reopened. What overturned it is that one of the
#   three closing decisions leaves nothing to buy: an approved person
#   already has what the fee purchases. The refusal is in submit_kyc,
#   reads User.kyc_status, and answers kyc_already_verified.
#
#   kyc/constants.py and kyc/models.py state the same rule in passing
#   and now point here instead of repeating it -- two full copies of
#   one fact are two things to correct, and the first correction
#   leaves the second lying.
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

import asyncio
from dataclasses import dataclass
from typing import BinaryIO
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
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
    KYC_MIME_SIGNATURES,
    KYC_PRESIGNED_URL_TTL_SECONDS,
    KYC_SIGNATURE_PROBE_BYTES,
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


async def _load_settings_row(session: AsyncSession) -> KYCSettings | None:
    """Read the single settings row, or None when nobody has written it.

    Shared by the reader and the writer so that the writer's retry after
    a lost race asks exactly the same question as its first read.
    """
    stmt = select(KYCSettings).where(KYCSettings.id == KYC_SETTINGS_ID)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_verification_mode(session: AsyncSession) -> str:
    """The mode in force, or the default when nothing has been set.

    NO ROW IS THE NORMAL STATE, not an error: every box starts empty
    and stays that way until a staff member first moves the switch.
    Manual is the default because manual is what works -- an untouched
    switch must not put the product into the state whose other half has
    not shipped.
    """
    settings_row = await _load_settings_row(session)

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

    THE FIRST WRITE IS A RACE, AND THE LOSER IS A SECOND UPDATE RATHER
    THAN A 500. The row has one constant primary key, so "read, find
    nothing, insert" is safe only until two staff members save for the
    first time at once: the second INSERT hits the primary key and used
    to leave the endpoint as an IntegrityError. The insert now runs on
    a SAVEPOINT (the pattern referrals/service.py already uses); when it
    collides the savepoint rolls back on its own, the outer transaction
    survives, and the row the winner committed is read and updated.

    The re-read is what keeps the audit honest. Under READ COMMITTED the
    second SELECT takes a fresh snapshot, so the loser records the
    winner's mode as `from` -- which is what actually preceded its own
    write. Reusing the "manual" it read the first time would log a
    transition that never happened.
    """
    settings_row = await _load_settings_row(session)

    if settings_row is None:
        old_mode = VerificationMode.MANUAL
        settings_row = KYCSettings(
            id=KYC_SETTINGS_ID,
            verification_mode=mode,
            updated_by_id=actor_id,
        )
        try:
            async with session.begin_nested():
                session.add(settings_row)
                await session.flush()
        except IntegrityError:
            # Lost the race. The savepoint took the pending row with it,
            # so the identity map is clean and the row the winner wrote
            # is now visible to this transaction.
            settings_row = await _load_settings_row(session)
            if settings_row is None:
                # The signature allows None; the database does not. A
                # collision on this primary key means the row is there,
                # and no path in this module deletes it. Re-raise the
                # original error rather than invent a route out of a
                # state the storage cannot produce.
                raise
            logger.info(
                "kyc_verification_mode_first_write_raced",
                actor_id=str(actor_id),
            )
            old_mode = settings_row.verification_mode
            settings_row.verification_mode = mode
            settings_row.updated_by_id = actor_id
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


def validate_document_signature(
    stream: BinaryIO,
    *,
    content_type: str,
    kind: str,
) -> None:
    """Refuse a file whose first bytes disagree with its own extension.

    THE NAME IS THE UPLOADER'S, THE BYTES ARE THE FILE'S. Everything
    upstream of this point trusts the extension: validate_document_
    filename resolves the MIME type from it, build_document_storage_key
    takes the stored extension from that type, and upload_object writes
    the object with it as ContentType. So until this check existed, a
    file of any nature named passport.jpg was stored, served and
    recorded as image/jpeg -- permanently, because this module has no
    delete path and keeps documents on purpose.

    It is also what issue_document_url leans on when it presigns
    without Content-Disposition: attachment; read its docstring before
    weakening this one.

    Reads the head of the stream and rewinds it, so the caller can hand
    the same stream to the upload afterwards.

    Raises:
        BadRequestError: the head does not match the claimed type.
    """
    signatures = KYC_MIME_SIGNATURES[content_type]

    head = stream.read(KYC_SIGNATURE_PROBE_BYTES)
    stream.seek(0)

    if any(head.startswith(signature) for signature in signatures):
        return

    extension = KYC_ALLOWED_MIME_TYPES[content_type]
    raise BadRequestError(
        f"The {kind} image is not a {extension.upper()} file, whatever "
        f"its name says. Upload the photo itself, not a renamed file.",
        code="kyc_document_content_mismatch",
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

    TWO CASES THAT LOOKED THE SAME AND ARE NOT. An empty list is a
    legitimate answer for an application that exists: the ones
    decide_by_user() creates for a person approved by hand have no
    documents and never will. An application id that matches nothing is
    a different fact, and returning the same empty list for it told
    staff "this session carries no images" about a session that does
    not exist -- so a mistyped or stale id read as a real answer.

    An unknown id is now a 404; an existing application with no
    documents is still an empty list.

    Raises:
        NotFoundError: no application carries this id.
    """
    exists = await session.execute(
        select(KYCApplication.id).where(KYCApplication.id == application_id)
    )
    if exists.scalar_one_or_none() is None:
        raise NotFoundError("KYC application not found")

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

    SHOWN IN THE BROWSER, NOT HANDED OVER AS A FILE, AND THAT IS A
    CHOICE. generate_presigned_url takes download_filename and turns it
    into Content-Disposition: attachment, which its own docstring calls
    the primary defence against stored-XSS through a payload uploaded
    under a trusted extension. This path passes no filename on purpose:

      * the act here is LOOKING at a passport next to a decision, and an
        attachment turns every check into a download into the reviewer's
        Downloads folder -- copies of other people's identity documents
        on staff laptops, which is worse than what it prevents;
      * there is no name to give. KYCDocument deliberately stores no
        original filename (see its docstring: the uploader's string
        routinely carries the person's real name), so the header would
        have to invent one;
      * the vector Content-Disposition defends against is closed at the
        door instead. validate_document_signature() in this module
        refuses any upload whose first bytes are not the JPEG or PNG
        magic number, so nothing but a real image reaches storage.

    THAT LAST POINT IS THE LOAD-BEARING ONE. Whoever removes or weakens
    validate_document_signature re-opens exactly what this decision
    leans on, and the signature check is in a different function with a
    different reason for existing -- so the connection is stated here
    rather than left to be rediscovered.

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

    Order is deliberate, and H12 added a step to it, H13 another. An
    already-approved person is refused first of all, then the document
    type, then the advisory lock, then the conflict check, then the
    balance check, then the documents are checked as a SET, then every
    write. Two concurrent submits serialise on the lock, so the second
    one sees the first one's debit and is refused instead of charging
    twice against the same ten dollars.

    THE APPROVED REFUSAL STANDS BEFORE THE REQUEST IS EVEN LOOKED AT,
    and that placement is the point. Whether this person has anything
    to buy does not depend on whether they picked the right files:
    telling a verified person "your selfie is missing" would send them
    off to fix a submission that must not happen at all. It is not
    duplicated in the router -- the body is already buffered by the
    time either could run (see the KNOWN CEILING marker in
    kyc/router.py), so a second copy would save parsing, not traffic,
    and would be a second place holding one rule. The service is also
    what the seed script and any future caller reach, and they never
    pass through the router.

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

    THE THREE UPLOADS RUN CONCURRENTLY, NOT ONE AFTER ANOTHER (H17
    P-58). The advisory lock above is keyed on this user and is also
    what purchases and instalment tranches take, so a slow upload used
    to hold every other money operation of this person's for as long
    as the slowest CHAIN of sequential PUTs took, not the slowest
    single one. Storage keys are computed for every document before
    any upload starts (`_planned_uploads` below), so a mid-flight
    failure never leaves a later key uncomputed. The gather is called
    with `return_exceptions=True` on purpose: every upload is awaited
    to completion regardless of outcome, so the `already_written` list
    a failure logs is read off the actual set of successes rather than
    guessed from how far a loop got. Two documents can now fail at
    once in a way they never could sequentially -- a total storage
    outage used to fail on the first document only, because the old
    loop never reached the second -- and when that happens the
    exception raised is always the one belonging to the first document
    in `documents`, for the same reason the checks above run in a
    fixed order: a predictable failure is easier for a caller to
    reason about than a fast one.

    THE MODE IS RECORDED, NOT ACTED ON. `verification_mode` is written
    to the row and nothing branches on it: the provider integration is
    the next pass, so a manual decision is the only decision there is.
    Recording it now means the rows this pass creates say truthfully
    how they were decided instead of being backfilled with a guess.

    Raises:
        ConflictError: this person is already verified
            (kyc_already_verified), or a session is already open for
            them (kyc_already_in_progress). The two codes are distinct
            because the two situations lead to different screens: one
            is finished, the other is waiting.
        InsufficientBalanceError: balance below the fee.
        BadRequestError: the document set is wrong for this type.
        StorageError: an upload failed; nothing is committed.
    """
    if user.kyc_status == KYCStatus.APPROVED:
        # The message travels to the person verbatim: the verification
        # screen prints the server's text as-is (frontend, api/client
        # ApiResponseError.detail), so this is interface copy, not a
        # log line.
        raise ConflictError(
            "Your identity has already been verified. There is nothing "
            "more to send us -- you can go straight to the platform.",
            code="kyc_already_verified",
        )

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

    # H17 P-58. Keys are computed for every document up front, before
    # any upload starts -- see the docstring paragraph above. Nothing
    # here reads or writes the session, so running the uploads
    # concurrently touches no shared state: each upload_object() call
    # opens its own short-lived client (core/storage.py), and each
    # pending.stream is a distinct file-like object.
    _planned_uploads: list[tuple[PendingDocument, UUID, str]] = []
    for pending in documents:
        document_id = uuid4()
        storage_key = build_document_storage_key(
            application.id, document_id, pending.content_type
        )
        _planned_uploads.append((pending, document_id, storage_key))

    # return_exceptions=True, not the bare default. With the default,
    # gather raises as soon as the first task fails and the still-running
    # tasks are abandoned rather than cancelled -- their outcome is then
    # unknown, which is exactly the information already_written below
    # needs. Waiting for every result first makes the log line true.
    _upload_results = await asyncio.gather(
        *(
            upload_object(
                storage_key,
                pending.stream,
                pending.content_type,
                content_length=pending.size_bytes,
            )
            for pending, _document_id, storage_key in _planned_uploads
        ),
        return_exceptions=True,
    )

    _failures = [
        (pending, storage_key, result)
        for (pending, _document_id, storage_key), result in zip(
            _planned_uploads, _upload_results, strict=True
        )
        if isinstance(result, BaseException)
    ]

    if _failures:
        # Let the first one out, by input order, not by whichever
        # finished failing first -- see the docstring paragraph above
        # for why a fixed order is chosen over completion order.
        # The transaction has not committed, so the application row,
        # the ledger entry and the transaction row all disappear with
        # it and the person keeps their money. Objects already written
        # for this attempt stay behind unreferenced -- named here
        # rather than swept, because a sweep would be a second failure
        # path to get right for an object nothing can reach.
        first_pending, first_key, first_exc = _failures[0]
        already_written = [
            storage_key
            for (_pending, _document_id, storage_key), result in zip(
                _planned_uploads, _upload_results, strict=True
            )
            if not isinstance(result, BaseException)
        ]
        logger.error(
            "kyc_document_upload_failed",
            application_id=str(application.id),
            kind=first_pending.kind,
            storage_key=first_key,
            already_written=already_written,
            also_failed=[
                {"kind": pending.kind, "storage_key": storage_key}
                for pending, storage_key, _exc in _failures[1:]
            ],
        )
        raise first_exc

    for pending, document_id, storage_key in _planned_uploads:
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
        # SECOND KEY BECAUSE created_at TIES. It comes from
        # server_default=func.now(), which is the TRANSACTION's start
        # time, so two rows written in one transaction carry the same
        # stamp and "the newest" stops being a question the ORDER BY can
        # answer. WHAT id.desc() BUYS IS REPRODUCIBILITY, NOT RECENCY:
        # KYCApplication has no monotonic column at all -- the id is a
        # uuid4 -- so a tie resolves the same way on every run and in
        # every replica, but the winner is not the later row. Do not
        # build "most recent" on this tie-break.
        .order_by(KYCApplication.created_at.desc(), KYCApplication.id.desc())
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

    "FROM" IS READ OFF THE USER, NOT OFF THE ROW (H13). It used to be
    `application.status`, which was true only while every decision was
    written onto the row the person's previous decision already sat on.
    It was already false on the branch that CREATES a row: that row is
    born carrying the new status, so a person approved from
    NOT_STARTED was audited "from: approved, to: approved". P-53 made
    the same thing happen to an approval after a rejection, which is
    the transition most worth reading correctly. The audit row is
    addressed to the user (target_type="user"), so the user's previous
    status is what it is claiming; taking it from the user is also what
    submit_kyc has always done. Do not put `application.status` back
    because it looks obvious -- it answers a different question, and
    for a freshly created row it answers nothing.
    """
    old_status = user.kyc_status
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

    Creates a new application row unless the newest one is a row this
    decision is entitled to write on -- the open session it decides, or
    the approval a revocation withdraws. See the comment at the
    predicate below; a terminal row is never rewritten. The new row
    already carries the decision, so user.kyc_status and the
    application history never disagree, including for an imported
    account approved before this table had a row for them.

    SERIALISED PER PERSON (H18 P-60b). Two concurrent calls for the
    same user_id used to both pass the not-already-decided checks below
    and both write a row -- see the advisory lock taken right after
    input validation, on the same key submit_kyc uses.

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

    # H18 P-60b. Same key submit_kyc takes, so a submit and a manual
    # decision on the same person serialise instead of passing through
    # each other. Without this, two concurrent calls here (e.g. a
    # double-click, or a decision racing a submit) could both read
    # user.kyc_status before either commits and both pass the
    # not-already-decided checks below, producing two APPROVED rows
    # instead of one (H13 report). No new branch is needed to handle the
    # loser: every read below runs AFTER the lock, in this request's own
    # session, so the loser's SELECT sees whatever the winner already
    # committed and lands in one of the existing ConflictErrors on its
    # own -- a real refusal, not an integrity error.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": user_id.int & 0x7FFFFFFFFFFFFFFF},
    )

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
        # Second sort key, for the reason and with the caveat spelled
        # out in get_kyc_status: created_at ties inside one transaction,
        # and id.desc() buys reproducibility, not recency.
        .order_by(KYCApplication.created_at.desc(), KYCApplication.id.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    application = result.scalar_one_or_none()

    # WHICH ROW A DECISION IS ALLOWED TO OVERWRITE (H13 P-53). Until
    # this pass the answer was "the newest one, whatever it says", and
    # only the complete absence of a row created a new one. So a person
    # who paid, uploaded a passport and a selfie and was REJECTED had
    # that very row turned into APPROVED when staff later approved them
    # by hand: the kyc_documents submitted for a refused session became
    # the stated basis of the approval, the row's document_type
    # travelled with it, and transactions.reference_id pointed at a row
    # asserting the opposite of what had been paid for.
    #
    # Exactly two situations may write onto an existing row:
    #
    #   SUBMITTED -- the decision this session was opened and paid for.
    #       Writing it anywhere else would leave the paid session
    #       forever undecided.
    #   APPROVED, when the decision is REVOKED -- a withdrawal is by
    #       construction a SECOND decision on the row it withdraws.
    #       _write_decision's idempotency_key carries the status for
    #       precisely this reason; making a revocation open a new row
    #       would be a regression, not a side effect.
    #
    # Everything else gets a new row, including the case where there is
    # no row at all. The new row is born carrying the decision rather
    # than passing through SUBMITTED -- passing through would make the
    # history claim a fee was charged, and this path is free -- and its
    # document_type stays NULL, which is the honest statement that this
    # decision rests on no submitted document. It is nullable for that
    # reason (see kyc/models.py), so no migration is involved.
    may_reuse = application is not None and (
        application.status == KYCStatus.SUBMITTED
        or (
            application.status == KYCStatus.APPROVED
            and new_status == KYCStatus.REVOKED
        )
    )

    if not may_reuse:
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
