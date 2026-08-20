# =============================================================================
# AIVIS.ONE Backend -- Transactional Outbox: relay to comms (T-63)
# =============================================================================
#
# Background loop: ships pending OutboxEvent rows (T-62) to the comms
# Redis Stream, strictly in id order, in batches, marking published_at.
# Lives in the app lifespan behind the comms_relay_enabled switch AND a
# non-empty comms_redis_url.
#
# WIRE (frozen comms contract, comms app/transport/events.py):
#   XADD <COMMS_EVENTS_STREAM> * event <name> data <UTF-8 JSON>
# The stream name defaults to the comms consumer's own default
# (comms app/core/config.py:66 `comms_events_stream: str =
# "comms:events"`). The consumer creates the consumer group itself with
# XGROUP CREATE ... MKSTREAM at id "0" (comms app/transport/consumer.py),
# so this relay may publish into a stream that has never had a reader --
# nothing is lost, the first consumer to start reads from the beginning.
#
# NOTHING EMITS YET. No product code calls emit_event in this tree; the
# first emitter is a later delivery. After this one the pipe exists and
# turns, and on a box whose .env carries COMMS_REDIS_URL it starts
# turning at the next restart.
#
# ERROR MODEL -- the substance of this file:
#
#   - PER-EVENT failure (a poison row: this event's own XADD is
#     rejected) -> attempts += 1 on THAT row, and the REST of the batch
#     still publishes. One poison event must not head-of-line block the
#     whole outgoing pipe. The row is NEVER dropped; it gets an
#     exponential backoff so it stops re-trying on every tick, and a
#     WARNING every comms_relay_warn_every_attempts failures so the
#     operator sees poison in the log rather than a silent loop.
#
#   - CONNECTION-level failure (the comms Redis is unreachable, or
#     answers with a refusal) aborts the pass WITHOUT touching attempts.
#     An outage is not the rows' fault: a row that never got a fair try
#     must not be charged for one, or an hour of downtime would walk
#     healthy rows straight to the dead-letter ceiling. The outbox waits
#     the outage out and the next tick retries; state lives in the table,
#     so a restart resumes where the last committed pass ended.
#
#   - AT THE CEILING the row is marked dead and published_at stays NULL,
#     because the truth of that state is that the row was never shipped.
#
# ORDERING: within a pass rows publish in id order. A poison row being
# skipped (or waiting out a backoff) means later rows of the same pass
# still publish -- a momentary inversion, accepted: the alternative is a
# single bad row stopping every event behind it.
#
# CONCURRENCY: FOR UPDATE SKIP LOCKED -- a second app replica running its
# own relay claims disjoint rows instead of double-publishing the same
# ones.
#
# SESSION RULES: the pass functions own NO transaction. Production opens
# and commits its own; tests inject a session and own commit/rollback.
# =============================================================================

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from redis import asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError as RedisResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import CursorResult, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session_factory
from app.core.events.models import (
    _NOT_YET_REDACTED_SQL,
    PAYLOAD_RETENTION_DAYS,
    REDACTED_PAYLOAD,
    OutboxEvent,
)

logger = structlog.get_logger()

# Envelope field names (mirror of the frozen comms contract).
_ENVELOPE_EVENT_FIELD = "event"
_ENVELOPE_DATA_FIELD = "data"

# Redis errors that mean "the pipe is down", not "this event is bad".
_CONNECTION_ERRORS = (RedisConnectionError, RedisTimeoutError, OSError)

# THE CRITERION for what belongs in an infrastructure branch (this tuple,
# or the ResponseError clause in _publish_batch): does the exception
# describe the STATE OF THE INFRASTRUCTURE (unreachable, refused,
# misconfigured), or the BADNESS OF THIS EVENT (its own payload or shape
# rejected on its own terms)? The former is charged no attempts and gets
# no dead-letter -- the row deserves a fair try once the state clears.
# The latter is poison and must keep paying for itself, or a genuinely
# bad row loops forever.
#
# ┌─ KNOWN CEILING ──────────────────────────────────────────────────────
# │ (1) MECHANICS: ResponseError is Redis ANSWERING, not Redis being
# │     unreachable -- OOM under maxmemory, READONLY on a failed-over
# │     replica, an ACL rejection, a missing module. All of those are
# │     infrastructure state rather than this event's fault, so
# │     ResponseError gets its own except clause (charging no attempts,
# │     setting no dead_lettered_at -- the same outcome as the connection
# │     branch) under its OWN log key: "unreachable" would send an
# │     operator to fix a Redis that is alive and answering.
# │ (2) STATUS: acknowledged by design.
# │ (3) REFERENCE: none in this tree, and there is nothing to file. The
# │     classification is inherited from the reference implementation,
# │     where it WAS a fix (ResponseError used to fall into the poison
# │     branch and dead-lettered healthy events); aivis never shipped
# │     that defect, so there is no aivis ticket to point at.
# │ (4) UNCONSERVATION TRIGGER: this file grows a pipeline, an
# │     EVAL/EVALSHA call, or Redis cluster mode. Only then do
# │     ResponseError's OTHER subclasses become reachable here --
# │     ExecAbortError (a queued MULTI/EXEC command failed),
# │     NoScriptError (EVALSHA on an unloaded script), and the cluster
# │     topology family (MovedError, AskError, ClusterDownError and
# │     friends) -- and some of those describe THIS command's shape, not
# │     the state of the infrastructure.
# │ (5) SHAPE OF THE FIX: narrow the except clause from the whole
# │     ResponseError class down to the specific infra-shaped subclasses
# │     that still apply once the trigger above has happened.
# │ (6) REJECTED, AND WHY -- the price paid today: ResponseError CAN
# │     depend on an event's own content (an XADD argument larger than
# │     proto-max-bulk-len is refused as a ResponseError on that specific
# │     row). Charging such a case to the infrastructure branch means the
# │     `break` below halts the WHOLE pass at that row on every tick,
# │     forever, because the id-order scan re-selects it first every
# │     time. What limits the exposure today: the relay issues exactly
# │     one Redis command (XADD) with no pipeline, no scripting and no
# │     cluster, so the causes of a ResponseError here can be enumerated
# │     -- see (1). The way out of a genuinely content-caused case is a
# │     human reading outbox_relay_redis_rejected and acting on the row.
# └─────────────────────────────────────────────────────────────────────

# The redaction pass runs on its own slow cadence, deliberately unrelated
# to the publish interval: shipping is what this loop exists for, tidying
# is a passenger. An hour costs a redacted row up to one extra hour of
# life beyond its retention window, and costs the loop one indexed
# UPDATE.
_REDACTION_INTERVAL_SECONDS = 3600

# Rows per redaction pass. The first run after rollout meets whatever the
# table has accumulated, and an unbounded UPDATE there is a long lock on
# the queue the product writes into. Bounded, a backlog drains over a few
# passes instead; the remainder is simply the next pass's work.
_REDACTION_BATCH_SIZE = 1000

# Monotonic clock, not wall time: this measures an interval only, and a
# clock step (NTP, a misconfigured host) must not skip a pass or stall
# one for hours. None = "never run in this process", so the first pass
# happens at startup.
_last_redaction_at: float | None = None


def build_envelope(event: OutboxEvent) -> dict[str, str]:
    """Assemble the wire envelope {event, data} for one outbox row."""
    return {
        _ENVELOPE_EVENT_FIELD: event.event_type,
        _ENVELOPE_DATA_FIELD: json.dumps(event.payload, ensure_ascii=False),
    }


async def _publish_batch(
    session: AsyncSession,
    redis: aioredis.Redis,
) -> tuple[int, int]:
    """The transaction-agnostic core of one relay pass.

    Selects pending rows FOR UPDATE SKIP LOCKED inside the CALLER'S
    transaction, XADDs them in id order, marks published_at / charges
    attempts. Owns no transaction: the caller commits (production) or
    rolls back (tests). See the module header for the error model.

    Returns (published, failed) for the pass.
    """
    published = 0
    failed = 0
    # One aware `now` per pass: the readiness filter and every assignment
    # below share it, so a row cannot be judged against one clock reading
    # and stamped with another.
    now = datetime.now(UTC)
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.published_at.is_(None),
            # Dead rows leave the pipe for good (see the ceiling marker
            # in the failure branch below)...
            OutboxEvent.dead_lettered_at.is_(None),
            # ...and a backed-off poison row waits out its delay while
            # ready rows keep shipping in id order.
            or_(
                OutboxEvent.next_attempt_at.is_(None),
                OutboxEvent.next_attempt_at <= now,
            ),
        )
        .order_by(OutboxEvent.id)
        .limit(settings.comms_relay_batch_size)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    events = list(result.scalars().all())

    for event in events:
        try:
            await redis.xadd(
                settings.comms_events_stream,
                build_envelope(event),  # type: ignore[arg-type]
            )
        except _CONNECTION_ERRORS as exc:
            # Infrastructure, not poison: stop the pass, and do NOT
            # charge attempts to rows that never got a fair try.
            logger.warning(
                "outbox_relay_redis_unreachable",
                error=str(exc),
                pending_from_event_id=event.id,
            )
            break
        except RedisResponseError as exc:
            # Also infrastructure (see the ceiling marker above
            # _CONNECTION_ERRORS): Redis is reachable and answered, but
            # refused the write. Same outcome as the connection branch,
            # its own log key. Kept a SEPARATE clause rather than folded
            # into that tuple, whose name would then start lying.
            logger.warning(
                "outbox_relay_redis_rejected",
                error=str(exc),
                pending_from_event_id=event.id,
            )
            break
        except Exception as exc:
            # Poison row: charge it, keep the pipe moving.
            event.attempts += 1
            failed += 1
            if event.attempts >= settings.comms_relay_max_attempts:
                # Die LOUDLY, once: the select above excludes dead rows,
                # so this row can never fail again and the single-ERROR
                # guarantee holds by construction. published_at stays
                # NULL -- the truth of this state is "never shipped" --
                # and the dead get no backoff.
                #
                # ┌─ KNOWN CEILING ──────────────────────────────────────
                # │ (1) MECHANICS: a row marked here leaves the relay's
                # │     select forever, and this tree has NO way to bring
                # │     it back. The reference implementation keeps
                # │     administrative handles (list dead rows, requeue
                # │     them) in a separate module; that module is
                # │     deliberately not ported in this delivery. Until
                # │     it is, reviving a dead row means a human writing
                # │     SQL against outbox_events by hand. Its payload is
                # │     also retained indefinitely, because the redaction
                # │     pass only ever touches shipped rows (see
                # │     _redact_batch, which states that trade in full
                # │     rather than repeating this marker).
                # │ (2) STATUS: acknowledged by design.
                # │ (3) REFERENCE: none, and nothing to file yet. No
                # │     product code calls emit_event in this tree, so
                # │     the only rows that can die here are rows a test
                # │     wrote. An operator console with no operator is
                # │     code that rots untested; it ships with the first
                # │     emitter, not before it.
                # │ (4) UNCONSERVATION TRIGGER: the first
                # │     outbox_event_dead_lettered line in the log of a
                # │     real box, OR the first product caller of
                # │     emit_event landing in this tree -- whichever
                # │     comes first.
                # │ (5) SHAPE OF THE FIX: port the reference's separate
                # │     administrative module as its own file and its own
                # │     delivery -- list dead rows, requeue by id
                # │     (clearing attempts, next_attempt_at and
                # │     dead_lettered_at together). NOT a widening of the
                # │     select above: a dead row must stay out of the
                # │     pipe until a human decides otherwise.
                # │ (6) REJECTED, AND WHY. (a) Not dead-lettering at all:
                # │     a row that can never ship would then be retried
                # │     until the end of time, keeping a permanent
                # │     resident in the pending index and a permanent
                # │     line in the log. (b) Deleting the row: outbox
                # │     rows are never deleted (T-62), and destroying an
                # │     undelivered message together with the evidence of
                # │     why it would not go is unrecoverable. (c) Setting
                # │     published_at to get the row out of the way: that
                # │     is the dangerous one -- it would make "never
                # │     shipped" indistinguishable from "shipped", and
                # │     the redaction pass would then eat the payload of
                # │     a message that still has to be delivered.
                # └─────────────────────────────────────────────────────
                event.dead_lettered_at = now
                logger.error(
                    "outbox_event_dead_lettered",
                    event_id=event.id,
                    event_type=event.event_type,
                    attempts=event.attempts,
                    error=str(exc),
                )
                continue
            # Exponential backoff from the POST-increment attempts (first
            # failure -> base * 2). The exponent clamp guards float
            # overflow: attempts is unbounded in principle, since a
            # future requeue path would revive a row and let it fail on.
            delay = min(
                settings.comms_relay_backoff_base_seconds
                * 2 ** min(event.attempts, 30),
                settings.comms_relay_backoff_cap_seconds,
            )
            event.next_attempt_at = now + timedelta(seconds=delay)
            log = (
                logger.warning
                if event.attempts % settings.comms_relay_warn_every_attempts == 0
                else logger.info
            )
            log(
                "outbox_event_publish_failed",
                event_id=event.id,
                event_type=event.event_type,
                attempts=event.attempts,
                next_attempt_at=event.next_attempt_at.isoformat(),
                error=str(exc),
            )
            continue
        event.published_at = datetime.now(UTC)
        published += 1

    return (published, failed)


async def relay_pending_batch(
    redis: aioredis.Redis,
    *,
    session: AsyncSession | None = None,
) -> tuple[int, int]:
    """Publish one batch of pending outbox rows.

    Returns (published, failed) counts for the pass.

    Production (run_relay) calls it WITHOUT `session`: a fresh session
    and transaction are opened and COMMITTED, so published_at marks and
    attempts increments persist even though the emitting transactions are
    long gone.

    Tests inject their own `session` and emit without committing: the
    pass then runs entirely inside the test transaction, where a live
    relay in a server process could not see those rows anyway. The caller
    owns commit/rollback.
    """
    if session is not None:
        return await _publish_batch(session, redis)

    session_factory = get_session_factory()
    async with session_factory() as own_session, own_session.begin():
        return await _publish_batch(own_session, redis)


async def _redact_batch(session: AsyncSession) -> int:
    """Redact one batch of long-shipped payloads. Returns rows changed.

    Owns no transaction -- the caller commits (production) or rolls back
    (tests), the same contract as _publish_batch.
    """
    cutoff = datetime.now(UTC) - timedelta(days=PAYLOAD_RETENTION_DAYS)

    # The WHERE repeats the partial index's predicate VERBATIM and adds
    # the age bound on the indexed column. Both halves are load-bearing:
    # the planner only picks a partial index when it can prove the query
    # implies the index predicate, so dropping either one brings back the
    # sequential scan the index exists to remove.
    #
    # _NOT_YET_REDACTED_SQL is IMPORTED, not retyped, for exactly that
    # reason: the model builds its index predicate from this same string,
    # so "verbatim" holds by construction instead of by everyone
    # remembering. A local copy of the literal would be a fourth place to
    # keep in step, and the first edit that missed one would cost a full
    # table scan per pass with nothing failing anywhere.
    #
    # The marker comparison is also the idempotency guard -- and the two
    # are the same fact, not two checks that must be kept in step: a
    # redacted row stops matching the predicate and in doing so leaves
    # the index. A second pass over already-redacted rows changes nothing
    # because there is nowhere left for it to look.
    #
    # UNPUBLISHED ROWS ARE NEVER TOUCHED, whatever their age, and that is
    # the point of `published_at IS NOT NULL` rather than an accident of
    # it: for a row that never shipped, the payload is the ONLY copy of
    # what still has to be delivered and the only evidence of why it
    # would not go. Retaining data too long is a policy problem;
    # destroying an undelivered message is unrecoverable, and the two
    # costs are not symmetric.
    #
    # A DEAD-LETTERED row is the sharp edge of that rule: it keeps
    # published_at NULL by design, so its personal data is retained
    # indefinitely. That gap is stated in full at the dead-lettering
    # branch of _publish_batch (its ceiling marker owns the trigger and
    # the fix); it is named here so a reader of this predicate does not
    # have to discover it twice.
    #
    # ORM-only rules the app; this is a bulk UPDATE over an ORM entity,
    # not raw SQL. The literal marker is the one fragment that has to be
    # SQL text -- a bound parameter would leave the planner unable to
    # match the index predicate.
    victims = (
        select(OutboxEvent.id)
        .where(
            OutboxEvent.published_at.is_not(None),
            OutboxEvent.published_at < cutoff,
            text(_NOT_YET_REDACTED_SQL),
        )
        .order_by(OutboxEvent.published_at)
        .limit(_REDACTION_BATCH_SIZE)
        .scalar_subquery()
    )
    result = await session.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id.in_(victims))
        .values(payload=REDACTED_PAYLOAD)
        .execution_options(synchronize_session=False)
    )
    # session.execute() is typed as returning Result, whose interface has
    # no rowcount; a DML statement returns a CursorResult at runtime,
    # which does. The cast states that narrowing instead of reaching for
    # getattr, which would hide a real breakage behind a default of 0.
    return cast("CursorResult[Any]", result).rowcount or 0


async def redact_published_payloads(
    *,
    session: AsyncSession | None = None,
) -> int:
    """Redact one batch of payloads shipped more than the retention
    window ago. Returns the number of rows changed.

    Same session contract as relay_pending_batch: production calls it
    without `session` and gets its own committed transaction; tests
    inject one and own the commit/rollback.
    """
    if session is not None:
        return await _redact_batch(session)

    session_factory = get_session_factory()
    async with session_factory() as own_session, own_session.begin():
        return await _redact_batch(own_session)


def create_relay_redis() -> aioredis.Redis:
    """The relay's Redis connection, with socket timeouts.

    Extracted from run_relay for one reason: the timeout kwargs must be
    assertable without spinning the infinite loop. A hung TCP connection
    surfaces as a redis TimeoutError -- already in _CONNECTION_ERRORS,
    i.e. the INFRASTRUCTURE branch: pass aborted, attempts untouched.

    decode_responses is False on purpose, and differs from the app's own
    Redis client (core/redis.py, which decodes): this connection only
    ever writes an already-encoded JSON string, and the tests read the
    stream back as bytes exactly as the comms consumer does.
    """
    # The ignores mirror core/redis.py: redis-py's from_url is itself
    # untyped, so a strict caller has to say so at the call site.
    return aioredis.from_url(  # type: ignore[no-untyped-call, no-any-return]
        settings.comms_redis_url,
        encoding="utf-8",
        decode_responses=False,
        socket_connect_timeout=(settings.comms_relay_socket_connect_timeout_seconds),
        socket_timeout=settings.comms_relay_socket_timeout_seconds,
    )


async def _maybe_redact() -> None:
    """Run the redaction pass if its own interval has elapsed.

    Swallows everything: tidying may never take the pipe down with it.
    """
    global _last_redaction_at

    elapsed = asyncio.get_running_loop().time()
    if (
        _last_redaction_at is not None
        and elapsed - _last_redaction_at < _REDACTION_INTERVAL_SECONDS
    ):
        return
    _last_redaction_at = elapsed

    try:
        redacted = await redact_published_payloads()
    except Exception:
        # The clock is marked BEFORE the attempt, so a failing pass waits
        # out the full interval instead of retrying on every tick and
        # filling the log with the same traceback.
        logger.exception("outbox_redaction_pass_crashed")
        return

    if redacted:
        logger.info(
            "outbox_payloads_redacted",
            rows=redacted,
            retention_days=PAYLOAD_RETENTION_DAYS,
        )


async def run_relay() -> None:
    """The lifespan loop: connect, relay, sleep, repeat.

    Cancellation-safe: CancelledError propagates out of the sleep or the
    pass, and the finally block closes the connection. Outbox state lives
    in the table, so a restart resumes exactly where the last committed
    pass ended.
    """
    redis = create_relay_redis()
    logger.info(
        "outbox_relay_started",
        stream=settings.comms_events_stream,
        interval_seconds=settings.comms_relay_interval_seconds,
        batch_size=settings.comms_relay_batch_size,
    )
    try:
        while True:
            try:
                published, failed = await relay_pending_batch(redis)
                if published or failed:
                    logger.info(
                        "outbox_relay_pass",
                        published=published,
                        failed=failed,
                    )
            except _CONNECTION_ERRORS as exc:
                logger.warning("outbox_relay_redis_unreachable", error=str(exc))
            except Exception:
                # Database down, or an unexpected bug -- log loudly and
                # keep looping: the relay must outlive transient trouble.
                logger.exception("outbox_relay_pass_crashed")

            # Redaction runs AFTER publishing and never instead of it.
            # Three things keep the passenger from delaying the driver:
            # publishing runs first in every tick; this is gated to once
            # an hour rather than once a tick; and it has its own
            # try/except, so a failing UPDATE costs a log line and
            # nothing else. It is deliberately not a task, a timer or a
            # script -- the loop already turns.
            await _maybe_redact()

            await asyncio.sleep(settings.comms_relay_interval_seconds)
    finally:
        await redis.aclose()
        logger.info("outbox_relay_stopped")
