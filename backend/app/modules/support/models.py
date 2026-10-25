# =============================================================================
# AIVIS.ONE Backend -- Support: threads, tickets, the spam bin (T-65, H40)
# and the translation queue (H39 P-129, at the end of this file)
# =============================================================================
#
# TABLES AND THE QUESTION EACH ANSWERS.
#
#   support_threads -- WHICH comms threads are a person's support
#     conversation, and whose. One row per comms thread, however many a
#     person has (H40: a thread per ticket).
#   support_tickets -- WHAT a thread is to support: every appeal through
#     the support form is a ticket -- its own comms thread of kind
#     `ticket`, a topic and a category as CODES, our own status, the
#     operator who took it. One row per ticket thread; its key IS the
#     thread row's id. No message text, ever: the conversation is comms'.
#   support_spam_tombstones / support_thread_purges -- the spam bin
#     (purge.py): what is left of a deleted spam ticket, and the comms
#     threads still to be deleted in comms.
#   support_translation_jobs -- the translation queue (H39).
#
# WHY support_threads EXISTS AT ALL, AND WHY IT IS NOT A CONVENIENCE.
#
# comms has no client-side read surface we could trust for ownership: its
# routes take any thread id they are given and trust whatever actor the
# product sends. So this table is the ONLY source for two questions the
# product must answer without asking comms:
#
#   1. "which conversations are mine" -- the person's feed reads this
#      table and nothing else;
#   2. "is thread T mine" / "is T a support thread at all" -- checked
#      HERE, before any comms call, on every route that takes a thread id
#      from the wire. Without it a guessed thread id would open somebody
#      else's conversation.
#
# A THREAD WITHOUT A TICKET is the person's HISTORY: the one eternal `dm`
# thread support used before H40 (owner ruling: it stays history, no
# ticket after the fact). Nothing creates such a row any more -- every new
# support thread is born with its ticket, in the same transaction
# (service.py::create_ticket) -- so a person has at most the one history
# thread they already had, and it is read-only for operators.
#
# `comms_thread_id` is UNIQUE: it is the lookup key of both checks above,
# and the constraint is what turns a replayed appeal (the same thread back
# from comms under the same key) into "the ticket exists". `user_id` is no
# longer unique since H40 (migration 0060): a person has a thread per
# ticket.
#
# THE COMMS SECTION ID IS NEVER STORED HERE. It lives in comms' database
# and does not survive a comms teardown -- a persisted copy would go
# stale silently. It is resolved per process instead (service.py).
# =============================================================================

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import UUID as SA_UUID
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.mixins import TimestampMixin, UUIDMixin


class SupportThread(UUIDMixin, TimestampMixin, Base):
    """This product's pointer to one comms support thread of one person."""

    __tablename__ = "support_threads"

    # The person whose support conversation this is (comms' `client`).
    # Indexed, not unique (H40): a person has a thread per ticket.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The comms thread id. Opaque to us: we never parse it, only carry
    # it back to comms and compare it to what comms last told us.
    comms_thread_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        nullable=False,
    )

    __table_args__ = (
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
# Tickets (H40)
# ---------------------------------------------------------------------------

# Categories -- codes; the labels are the screens', in the reader's
# language. One per topic today; kept as their own column because the
# statistics (H41) and the operator's filter group by category, and a
# second topic can join a category without a migration of the tickets.
CATEGORY_PAYMENTS = "payments"
CATEGORY_WITHDRAWALS = "withdrawals"
CATEGORY_VERIFICATION = "verification"
CATEGORY_PURCHASES = "purchases"
CATEGORY_TECH = "tech"
CATEGORY_OTHER = "other"
CATEGORIES = (
    CATEGORY_PAYMENTS,
    CATEGORY_WITHDRAWALS,
    CATEGORY_VERIFICATION,
    CATEGORY_PURCHASES,
    CATEGORY_TECH,
    CATEGORY_OTHER,
)


@dataclass(frozen=True)
class Topic:
    """One topic of the support form: its category, and its label in the
    two profile languages -- read ONLY by the operator signals
    (service.py::_topic_lines), which comms renders and which cannot look a
    code up; every screen draws its own labels from the code."""

    category: str
    ru: str
    en: str


# THE ONE PLACE "topic -> category" lives (owner ruling, H40 section 1).
# The codes are the form's own values (frontend support screen); any known
# code is accepted from anyone.
TOPIC_OTHER = "other"
TOPICS: dict[str, Topic] = {
    "payments": Topic(
        CATEGORY_PAYMENTS, "Платежи и пополнение", "Payments and deposits"
    ),
    "withdrawal": Topic(CATEGORY_WITHDRAWALS, "Вывод средств", "Withdrawals"),
    "kyc": Topic(
        CATEGORY_VERIFICATION, "Верификация (KYC)", "Verification (KYC)"
    ),
    "purchases": Topic(
        CATEGORY_PURCHASES, "Покупки и документы", "Purchases and documents"
    ),
    "technical": Topic(CATEGORY_TECH, "Технический вопрос", "Technical question"),
    TOPIC_OTHER: Topic(CATEGORY_OTHER, "Другое", "Other"),
}

# Statuses (owner ruling, H40 item 4) -- ours. comms knows only `open` and
# `resolved` for a ticket: every status but OPEN is `resolved` there, and
# nothing ever moves a ticket's thread to `closed` (comms would tell the
# person).
STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
STATUS_REJECTED = "rejected"
STATUS_DUPLICATE = "duplicate"
STATUS_SPAM = "spam"
STATUSES = (
    STATUS_OPEN,
    STATUS_RESOLVED,
    STATUS_REJECTED,
    STATUS_DUPLICATE,
    STATUS_SPAM,
)
# Where an operator may move an OPEN ticket. Back to OPEN: a person's
# message (service.py::_post_and_route) or an operator's "back to work"
# (service.py::reopen_ticket).
CLOSING_STATUSES = (STATUS_RESOLVED, STATUS_REJECTED, STATUS_DUPLICATE, STATUS_SPAM)


def _sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class SupportTicket(TimestampMixin, Base):
    """One appeal through the support form: its thread, topic, category,
    status and the operator who took it. `created_at` is the date of the
    appeal.

    Room for H41 (the rating and the statistics) is left on purpose, not
    filled: who resolved it, the rating and its comment are columns H41
    adds to this row, as velo did over the same ticket.
    """

    __tablename__ = "support_tickets"

    # The ticket IS its thread: the key is the support_threads row's id.
    # DEFERRED for velo's reason (its models.py): deleting a person deletes
    # the thread by cascade and sets the taker NULL in one statement; the
    # check at commit sees the end state, the ticket gone with its thread.
    support_thread_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "support_threads.id",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        primary_key=True,
    )
    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Who took it (claim, assign). Their signal is theirs alone.
    claimed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    # Bumped by every change a status change must not miss -- a person's
    # message, a status change, a handover: an operator's write is a
    # compare-and-set on it, since comms is called between reading the
    # ticket and writing it.
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # -- The rating (H41) ------------------------------------------------
    #
    # The operator who LAST moved the ticket to RESOLVED: "who resolved" of
    # the row and the card. Back to work keeps it; the next RESOLVED
    # overwrites it; a later close of another kind leaves it standing (the
    # card then reads it as the last resolver).
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # One rating per ticket, by its person, asked for at RESOLVED (owner
    # ruling): 1..5 stars, an optional comment kept AS WRITTEN -- never
    # translated -- and when.
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # THE PERSON'S INTERFACE LANGUAGE when they rated (users.language,
    # normalized), NOT the language of the comment's text: nothing detects
    # the language a text is written in. It is the best guess a screen has,
    # and is labelled with it; it is set with the rating, comment or not.
    rating_locale: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Who had resolved the ticket WHEN it was rated: the operator the rating
    # is about. resolved_by_user_id may move on afterwards (back to work,
    # another operator resolves); the rating stays with whom it rated.
    rated_resolver_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            f"topic IN ({_sql_in(tuple(TOPICS))})",
            name="ck_support_tickets_topic",
        ),
        CheckConstraint(
            f"category IN ({_sql_in(CATEGORIES)})",
            name="ck_support_tickets_category",
        ),
        CheckConstraint(
            f"status IN ({_sql_in(STATUSES)})",
            name="ck_support_tickets_status",
        ),
        CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5",
            name="ck_support_tickets_rating",
        ),
        # A rating is a whole: the stars, when, and the language -- or none.
        CheckConstraint(
            "(rating IS NULL) = (rated_at IS NULL) "
            "AND (rating IS NULL) = (rating_locale IS NULL)",
            name="ck_support_tickets_rating_whole",
        ),
        CheckConstraint(
            "rating IS NOT NULL OR rating_comment IS NULL",
            name="ck_support_tickets_rating_comment",
        ),
        Index("ix_support_tickets_created", "created_at", "support_thread_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SupportTicket thread_row={self.support_thread_id} "
            f"topic={self.topic} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# The spam bin (H40 item 7; purge.py)
# ---------------------------------------------------------------------------


class SupportSpamTombstone(UUIDMixin, Base):
    """What is left of a spam ticket the bin emptied (owner ruling: after
    the deletion the statistics keep only the date and the category): the
    date of the appeal and its category -- nothing that names a person, a
    thread or an operator. Written in the transaction that deletes the
    ticket (purge.bury_spam); read by the statistics of H41."""

    __tablename__ = "support_spam_tombstones"

    appealed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            f"category IN ({_sql_in(CATEGORIES)})",
            name="ck_support_spam_tombstones_category",
        ),
        Index("ix_support_spam_tombstones_appealed", "appealed_at"),
    )


class SupportThreadPurge(Base):
    """A comms thread whose rows we have already deleted and comms has not
    yet: the second phase of emptying the spam bin. A row lives from the
    transaction that deletes the ticket until comms answers the DELETE
    (204, also for a thread already gone); comms down leaves it for the
    next step. `attempts` and `last_error_at` are there to be seen."""

    __tablename__ = "support_thread_purges"

    comms_thread_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), primary_key=True,
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class SupportOperatorMute(Base):
    """An operator whose comms category `staff_messages` is still to be
    muted (H40, owner ruling): the operator signals of H40 replace comms'
    own msg.support_message ping, so an operator is not sent that ping at
    all -- mute.py says why, and how the row is carried out.

    Written with the membership (service.emit_support_membership,
    member=True), in its transaction; deleted when comms has taken the
    mute. A row lives while comms cannot take it yet -- no recipient yet
    (the user_upserted still in the outbox), comms down -- and `attempts`
    and `last_error_at` are there to be seen. The person's deletion takes
    the row with it."""

    __tablename__ = "support_operator_mutes"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True,
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
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
