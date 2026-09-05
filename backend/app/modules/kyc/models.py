# =============================================================================
# AIVIS.ONE Backend -- KYC Models (Sprint 2.1, H12 documents)
# =============================================================================
#
# KYCApplication:
#   Records each KYC submission attempt. Multiple rows per user possible
#   (history: rejected -> resubmit -> approved).
#
# KYCDocument:
#   The files a session carries. A SEPARATE TABLE rather than columns on
#   the application, because an application without documents is a
#   legitimate row and always was: decide_by_user() creates one for a
#   person approved by hand, who never submitted anything. Columns would
#   have made that row carry three NULLs meaning "not applicable" that
#   are indistinguishable from three NULLs meaning "not uploaded yet".
#
# ONE ROW PER PAID SESSION (H10):
#   A row is opened when the fee is charged and carries the decision
#   that closes it. Returning to a session that is still SUBMITTED
#   costs nothing; only a terminal decision makes the next attempt a
#   new, paid row.
#
# ONE STATUS VOCABULARY, AND IT LIVES IN users/models.py (H12 P-46f):
#   This file used to declare KYCApplicationStatus with exactly the
#   members of KYCStatus next door -- two enums for one fact, and two
#   CHECK constraints kept level by whoever remembered. The enum is
#   gone; KYCStatus is imported. It stays in users/models.py rather
#   than moving here because moving it would edit six modules that have
#   no stake in this pass; that the vocabulary of an application lives
#   on the user model is a real debt, recorded in the H12 report's
#   Observations rather than paid here.
#
#   tests/test_kyc.py asserts that both CHECK constraints admit exactly
#   this enum's members. That test, not a convention, is what stops the
#   two columns drifting apart again.
#
# SYNC:
#   On every status change, kyc/service.py updates User.kyc_status
#   (denormalized cache) for fast eligibility checks without JOIN.
# =============================================================================

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin
from app.modules.kyc.constants import VerificationMode
from app.modules.users.models import KYCStatus

__all__ = ["KYCApplication", "KYCDocument", "KYCSettings"]


class KYCApplication(UUIDMixin, TimestampMixin, Base):
    """KYC verification application -- one row per submission attempt.

    History is preserved: rejected applications remain in the table,
    new submissions create new rows.
    """

    __tablename__ = "kyc_applications"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=KYCStatus.SUBMITTED,
        server_default=KYCStatus.SUBMITTED.value,
        nullable=False,
    )

    # WHICH PATH DECIDED THIS ROW, FIXED WHEN THE ROW IS CREATED and
    # never re-read from the setting afterwards. Staff can move the
    # platform switch at any moment; a row that resolved the mode at
    # decision time instead would let one click change how every
    # already-paid session is handled, and empty the queue nobody
    # emptied.
    #
    # Written 'manual' by every path in this pass, because manual is the
    # only path that exists until the provider lands. The column is here
    # now rather than then so that the rows this pass creates say
    # truthfully how they were decided, instead of being backfilled
    # later with a guess.
    decision_mode: Mapped[str] = mapped_column(
        String(20),
        default=VerificationMode.MANUAL,
        server_default=VerificationMode.MANUAL.value,
        nullable=False,
    )

    # NULL means "no documents were ever submitted for this row" -- the
    # decide_by_user() path, where staff approve a person who never
    # applied. Not a default: a default would make those rows claim a
    # passport was shown.
    document_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<KYCApplication id={self.id} user={self.user_id} "
            f"status={self.status} mode={self.decision_mode}>"
        )


class KYCDocument(UUIDMixin, TimestampMixin, Base):
    """One stored identity document belonging to one application.

    KEPT FOREVER, per the storage ruling: there is no expiry column, no
    sweeper, and no delete path anywhere in this module. Documents
    survive a rejection and a revocation on purpose -- "on what basis
    was this person approved" is asked after something happens, not
    before.

    NO ORIGINAL FILENAME COLUMN, and nothing derived from one. The
    uploader controls that string, it routinely carries the person's
    real name, and storing it would put that name into the object key,
    into every presigned URL, and into the audit rows that record who
    looked. The extension we serve under comes from the validated MIME
    type instead.
    """

    __tablename__ = "kyc_documents"
    __table_args__ = (
        # One front, one back, one selfie -- the natural key of the
        # thing. Two rows of the same kind for one application would
        # leave staff looking at whichever the query happened to order
        # first, with no way to tell it was a choice.
        UniqueConstraint(
            "application_id", "kind", name="uq_kyc_documents_application_kind"
        ),
        # Two rows must never name one object: a duplicate key means one
        # upload silently overwrote another person's document.
        UniqueConstraint("storage_key", name="uq_kyc_documents_storage_key"),
    )

    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("kyc_applications.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Full MinIO key. Long enough for the prefix plus two UUIDs plus an
    # extension with room to spare; not unbounded, because an unbounded
    # key is one a caller can grow until something else truncates it.
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # The VALIDATED type, not the multipart header's claim. Stored so a
    # later reader (and the provider pass) knows what it is serving
    # without re-deriving it from the key.
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # BigInteger to match the ledger's convention for byte/cent counts;
    # the value is capped far below it by validation.
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<KYCDocument id={self.id} application={self.application_id} "
            f"kind={self.kind}>"
        )


# The one row of kyc_settings, by a fixed id rather than a "pick the
# first row" query. A settings table with no key has to answer "which
# row" somehow, and every other answer is worse: LIMIT 1 silently picks
# a winner if a second row ever appears, and a singleton boolean with a
# unique index is a column that exists to apologise for the shape. A
# constant primary key makes a second row impossible at the database
# rather than by convention -- a concurrent first write loses on the
# key instead of creating a twin.
KYC_SETTINGS_ID: UUID = UUID("00000000-0000-0000-0000-00000000c0de")


class KYCSettings(UUIDMixin, TimestampMixin, Base):
    """Platform-level KYC configuration. Exactly one row, ever.

    A TYPED COLUMN, NOT A KEY/VALUE PAIR. The first draft of this was a
    generic platform_settings table with a string key and a string
    value -- which paid the whole price of an EAV shape (untyped value,
    meaning living in the reader, a CHECK constraint growing one clause
    per key) and bought none of its benefit, because adding a setting
    still needed a migration for that clause. Generalising for a class
    with one member. The second setting adds a column here, exactly the
    way every other table in this tree grows.

    Lives in the kyc module because the setting is KYC's: who decides a
    verification. A setting belonging to another module belongs in that
    module's tables, not in a shared bucket that makes every module
    reach across.
    """

    __tablename__ = "kyc_settings"

    # manual | automatic -- see VerificationMode. CHECK-constrained in
    # migration 0050, so a value the code cannot interpret cannot be
    # stored even by hand in psql, and the reader needs no branch for
    # one.
    verification_mode: Mapped[str] = mapped_column(
        String(20),
        default=VerificationMode.MANUAL,
        server_default=VerificationMode.MANUAL.value,
        nullable=False,
    )

    # Who moved it last. The audit log carries the full history; this
    # is so the settings screen can name somebody without querying the
    # audit feed. Nullable because a row created by the service's
    # get-or-create has no staff behind it yet.
    updated_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<KYCSettings verification_mode={self.verification_mode}>"
