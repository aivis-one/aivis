# =============================================================================
# AIVIS.ONE Backend -- Support: the local thread pointer (T-65) and the
# translation queue (H39 P-129, at the end of this file)
# =============================================================================
#
# WHY THIS TABLE EXISTS AT ALL, AND WHY IT IS NOT A CONVENIENCE.
#
# comms has no client-side read surface. Its thread list
# (GET /api/v1/threads) is OPERATOR-scoped -- visible(me) = assignee is
# me OR (section thread AND unassigned) -- so asking it for a user's own
# conversations returns the wrong set twice over: it hides the thread as
# soon as a staff member claims it, and it shows every UNCLAIMED thread
# in the pool, which belongs to other people. There is also no
# "get one thread by id" endpoint anywhere in that API; only the message
# feed takes a thread id.
#
# So this table is the ONLY source for two questions the product must
# answer without asking comms:
#
#   1. "which conversations are mine" -- the list endpoint reads this
#      table and nothing else;
#   2. "is thread T mine" -- checked HERE, before any comms call, on
#      every route that takes a thread id from the wire. comms trusts
#      whatever actor the product sends it, so without this check a
#      guessed thread id would open somebody else's conversation.
#
# ONE ROW PER USER. `user_id` is UNIQUE, mirroring the shape chosen in
# service.py (operator_kind="section", kind="dm", no subject_ref): comms
# itself dedups that combination to one eternal thread per (client,
# section) pair, and the constraint keeps this table honest under the
# same invariant instead of letting a second local row point at a thread
# that already has one.
#
# `comms_thread_id` is UNIQUE too, and for a different reason: it is the
# lookup key of the ownership check. Two rows carrying the same thread id
# would mean two users own one conversation, which is the exact failure
# this table exists to prevent.
#
# THE COMMS SECTION ID IS NEVER STORED HERE. It lives in comms' database
# and does not survive a comms teardown -- a persisted copy would go
# stale silently. It is resolved per process instead (service.py).
# =============================================================================

from datetime import datetime
from uuid import UUID

from sqlalchemy import UUID as SA_UUID
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin


class SupportThread(UUIDMixin, TimestampMixin, Base):
    """This product's pointer to one user's comms support thread."""

    __tablename__ = "support_threads"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The comms thread id. Opaque to us: we never parse it, only carry
    # it back to comms and compare it to what comms last told us.
    comms_thread_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_support_threads_user"),
        UniqueConstraint(
            "comms_thread_id", name="uq_support_threads_comms_id"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SupportThread id={self.id} user={self.user_id} "
            f"thread={self.comms_thread_id}>"
        )


# ---------------------------------------------------------------------------
# The translation queue (H39 P-129)
# ---------------------------------------------------------------------------
#
# One row per ATTEMPT to translate one support message into one language.
# NO TEXT: neither the message nor the translation is kept here -- both
# live in comms (the message in the thread, the translation as its
# variant). The row holds only what the product alone can do: tie a job
# key back to its message, remember that comms' variant request was
# written (request_written_at -- the listener's sweep retries until comms
# takes it), record the outcome, and remember that the person was told
# once that a reply could not be translated (user_notified_at). The
# mechanism and every decision are in modules/support/translation.py.
#
#   direction  to_support -- a person's message, into the support language;
#              to_user -- a staff reply, into the person's language.
#   outcome    NULL while the job is ours to wait for; then
#              variant     -- the translation was written as a variant;
#              not_needed  -- the model found it already in `locale`;
#              declined    -- written declined: the language is closed for
#                             this message for good (comms never replaces
#                             a variant);
#              failed      -- the job ended without an answer, or comms
#                             refused it at intake: retryable by staff;
#              retried     -- the answer could not be read, and the next
#                             attempt was queued automatically.
#
# `support_thread_id` names the pointer row the message's thread belongs
# to, not "the person's one conversation": nothing here assumes a person
# has one thread, so the tickets of H40 take the same queue.

TO_SUPPORT = "to_support"
TO_USER = "to_user"
DIRECTIONS = (TO_SUPPORT, TO_USER)

OUTCOME_VARIANT = "variant"
OUTCOME_NOT_NEEDED = "not_needed"
OUTCOME_DECLINED = "declined"
OUTCOME_FAILED = "failed"
OUTCOME_RETRIED = "retried"
OUTCOMES = (
    OUTCOME_VARIANT,
    OUTCOME_NOT_NEEDED,
    OUTCOME_DECLINED,
    OUTCOME_FAILED,
    OUTCOME_RETRIED,
)


def _sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class SupportTranslationJob(UUIDMixin, TimestampMixin, Base):
    """One attempt to translate one support message into one language."""

    __tablename__ = "support_translation_jobs"

    support_thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("support_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    comms_message_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), nullable=False,
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    # The variant's language: comms section 12's opaque token, always a
    # normalised primary subtag here (translation.normalize_language).
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    job_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_written_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("job_key", name="uq_support_translation_jobs_key"),
        UniqueConstraint(
            "comms_message_id", "locale", "attempt",
            name="uq_support_translation_jobs_attempt",
        ),
        CheckConstraint(
            f"direction IN ({_sql_in(DIRECTIONS)})",
            name="ck_support_translation_jobs_direction",
        ),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_sql_in(OUTCOMES)})",
            name="ck_support_translation_jobs_outcome",
        ),
        CheckConstraint(
            "attempt >= 1", name="ck_support_translation_jobs_attempt",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SupportTranslationJob key={self.job_key} "
            f"outcome={self.outcome}>"
        )
