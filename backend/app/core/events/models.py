# =============================================================================
# AIVIS.ONE Backend -- Transactional Outbox: OutboxEvent model (Phase 1 / T-62)
# =============================================================================
#
# A row in THIS table is written in THE SAME transaction as the domain
# change that caused it. A background relay then ships unpublished rows
# to the comms Redis Stream. Domain change committed <=> event
# committed; no distributed transaction, at-least-once by replay.
#
# THE RELAY DOES NOT EXIST YET (it is T-63), and neither does any caller
# of emit_event. After this delivery the table exists, one function can
# write to it, and nothing reads it. That is the intended state, not an
# unfinished one -- the relay is a separate failure surface and shipping
# it in the same delivery would make the two impossible to roll back
# apart.
#
# WHY BIGSERIAL (BigInteger + Identity), NOT the project-wide UUID pk:
#   the relay publishes strictly in id order, so a monotonically
#   increasing integer IS the publication order. Random UUIDs have no
#   order, and a timestamp is not unique. This is a deliberate,
#   documented deviation from UUIDMixin -- the one model in this tree
#   that does not take it.
#
# PAYLOAD is the event's `data` document of the FROZEN comms wire
# contract (comms app/transport/events.py), INCLUDING the required
# version field "v". The envelope {event, data} is assembled by the
# relay at publish time -- storing `data` alone keeps the row 1:1 with
# "everything that evolves lives inside data".
#
# LIFECYCLE COLUMNS:
#   published_at NULL   -> pending, the relay's scan predicate;
#   published_at ts     -> shipped;
#   attempts            -> failed publish attempts (observability plus
#                          a poison-row warning threshold; NEVER a drop
#                          limit -- outbox rows are not discarded);
#   next_attempt_at     -> exponential-backoff carrier. NULL means "may
#                          be picked up immediately", which is also the
#                          state of every row this migration creates, so
#                          no backfill is ever needed;
#   dead_lettered_at    -> NULL means alive. Set once, when attempts
#                          reaches the relay's limit; published_at stays
#                          NULL, because the truth of that state is that
#                          the row was never shipped.
#
# ROW LIFETIME AND PERSONAL DATA. The payload of a shipped row is a
# personal-data document -- a user snapshot, or the text parameters of a
# message to someone. What happens to it:
#
#   - THE SKELETON IS KEPT FOREVER. All seven columns other than payload
#     are not personal data, cost almost nothing, answer the audit
#     question that is actually asked ("did this event ever leave?"),
#     and keep id monotonic.
#   - THE PAYLOAD IS REDACTED PAYLOAD_RETENTION_DAYS after published_at,
#     replaced by REDACTED_PAYLOAD. The column is NOT NULL and the
#     marker is more honest than an empty object: it says something WAS
#     removed rather than that nothing was there.
#   - ROWS ARE NEVER DELETED. A delete invites the question "did it eat
#     something that mattered", and answering that costs tests forever;
#     redaction gives the whole value without the risk.
#   - UNPUBLISHED ROWS ARE UNTOUCHABLE, whatever their age: for a row
#     that never shipped, the payload is the only copy of what must
#     still be delivered and the only evidence of why it would not go.
#
# The pass that performs the redaction ships WITH the relay (T-63), on
# its own slow cadence -- no cron, no timer, no script. The constants
# and the index below are here now because the second index cannot be
# expressed without them, and because moving them later would mean
# rewriting this model in the next delivery.
#
# SESSION RULES: no commit here (P-01). emit_event() inserts into the
# caller's session and transaction.
# =============================================================================

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# What a redacted payload looks like, and the SQL that recognises one.
# Declared here, next to the column and the index that depend on them,
# and imported by the relay when it arrives -- the redaction predicate
# has to be written identically in three places (this index, the
# UPDATE's WHERE, the new value) or the index silently stops being used.
REDACTED_PAYLOAD: dict[str, Any] = {"redacted": True}
_REDACTED_PAYLOAD_SQL = "'{\"redacted\": true}'::jsonb"
_NOT_YET_REDACTED_SQL = f"payload <> {_REDACTED_PAYLOAD_SQL}"

# How long a shipped payload lives. A CONSTANT, not a setting: a knob
# nobody has asked to turn is a knob without a consumer.
PAYLOAD_RETENTION_DAYS = 7


class OutboxEvent(Base):
    """One outgoing event awaiting (or past) publication to comms."""

    __tablename__ = "outbox_events"

    # Publication order. See header for why not UUID.
    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        primary_key=True,
    )

    # Envelope event name (comms contract: notification_request /
    # user_upserted / group_changed / reminder_cancel). Width mirrors
    # the widest name with headroom; the known-set check lives in
    # service.emit_event.
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # The event `data` document (with "v"), JSON-scalar values only --
    # enforced at emit time, since JSONB would happily store what the
    # comms validator later dead-letters.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # Set ONLY by the relay's per-event (poison) failure branch; the
    # infrastructure branch never touches it -- an outage is not the
    # row's fault. timezone=True mirrors published_at: every comparison
    # in this table is aware UTC.
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    __table_args__ = (
        # The relay's steady-state scan is
        # `WHERE published_at IS NULL ORDER BY id` -- index only the
        # pending tail, not the ever-growing published history.
        Index(
            "ix_outbox_events_unpublished",
            "id",
            postgresql_where=published_at.is_(None),
        ),
        # The redaction pass runs the OPPOSITE predicate, which the
        # index above by construction does not cover -- without this one
        # every pass is a sequential scan of a table that only grows.
        #
        # WHY THE PREDICATE IS THE WORK ITSELF, and not the obvious
        # `published_at IS NOT NULL`: that obvious form would index the
        # entire shipped history, so the index would grow monotonically
        # exactly like the table -- correct today, a tax forever. With
        # "not yet redacted" in the predicate a row LEAVES the index the
        # moment it is redacted, so the index only ever holds the window
        # of rows still awaiting work -- roughly PAYLOAD_RETENTION_DAYS
        # of traffic, no matter how many years the table has run.
        #
        # The age boundary is deliberately NOT here: now() is not
        # IMMUTABLE and Postgres would reject it in an index predicate.
        # That restriction is what keeps the index non-degrading, so it
        # costs nothing -- the age comparison becomes a range scan on
        # published_at, the indexed column.
        #
        # The relay's UPDATE must repeat both conditions verbatim. The
        # planner only uses a partial index when it can prove the
        # query's predicate implies the index's; a WHERE carrying just
        # the date would not be matched and the scan would come back.
        Index(
            "ix_outbox_events_pending_redaction",
            "published_at",
            postgresql_where=text(
                f"published_at IS NOT NULL AND {_NOT_YET_REDACTED_SQL}"
            ),
        ),
    )

    def __repr__(self) -> str:
        state = "published" if self.published_at else "pending"
        return (
            f"<OutboxEvent id={self.id} type={self.event_type} "
            f"{state} attempts={self.attempts}>"
        )
