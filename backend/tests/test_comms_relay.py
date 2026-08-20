# =============================================================================
# AIVIS.ONE Backend -- Outbox relay tests (T-63)
# =============================================================================
#
# What is fixed here is the ERROR MODEL, because that is the part of the
# relay whose defects are invisible in production: a row charged for an
# outage walks to the dead-letter ceiling on its own, and nothing raises.
#
# Covers:
#   1:  two rows publish in id order and both get published_at; a second
#       pass over the same transaction ships nothing (repeat axis)
#   2:  an empty outbox issues no XADD at all (emptiness axis)
#   3:  a poison row is charged and backed off while the REST of the
#       batch still publishes
#   4:  a connection failure aborts the pass and charges NOTHING; the
#       next pass ships the row untouched
#   5:  a Redis refusal (ResponseError) is infrastructure too, not poison
#   6:  the attempts ceiling marks the row dead ONCE, leaves published_at
#       empty, and takes the row out of the relay's select
#   7:  redaction touches shipped rows past the window and nothing else --
#       not fresh ones, not pending ones, not dead-lettered ones -- and a
#       repeat pass changes nothing
#   8:  the envelope matches the frozen comms contract, and a payload
#       carrying nothing but its version still ships (the relay is
#       transport, not a validator -- shortage axis)
#   9:  the relay's Redis connection carries its socket timeouts
#
# NO USERS, NO HTTP, NO BAND. Every row here is written through
# emit_event on db_session and identified by a SYNTH-prefixed
# recipient_id; nothing touches the auth layer, so no telegram_id range
# is claimed.
#
# NOTHING IS COMMITTED. Rows are emitted and the pass runs inside the
# test's own transaction, which is rolled back at the end -- the same
# discipline as tests/test_outbox_events.py (T-62).
#
# WHY THERE IS NO "PARK THE FOREIGN ROWS" HELPER HERE. The reference
# implementation shields its relay tests from rows other suites commit,
# because over there a live relay and real emitters share one outbox. In
# this tree no product code calls emit_event yet and the test client
# (ASGITransport) never fires the lifespan, so no relay runs and no other
# suite writes to outbox_events. Tests 1-2 assert exact counts, which
# means a foreign committed row would fail them loudly rather than
# quietly change what they measure. THE FIRST DELIVERY THAT ADDS A
# PRODUCT EMITTER should re-read this paragraph: from that point the
# shielding is needed.
#
# Redis is not faked. The relay's client is passed in explicitly, so
# these tests use the application's own test Redis with a throwaway
# stream name and introduce failures by patching xadd on the live client
# -- the same approach as the reference. The reference has NO redaction
# tests at all; tests 7 is written from the model's stated rules, not
# ported.
# =============================================================================

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from redis import asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError as RedisResponseError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import (
    PAYLOAD_RETENTION_DAYS,
    REDACTED_PAYLOAD,
    OutboxEvent,
)
from app.core.events.relay import (
    build_envelope,
    create_relay_redis,
    redact_published_payloads,
    relay_pending_batch,
)
from app.core.events.service import EVENT_GROUP_CHANGED, emit_event

# Marks the rows of this suite, so assertions can tell them apart from
# anything a future delivery leaves in the table.
SYNTH = "t63-relay-"

# A stream nobody consumes. Its name is deliberately not the configured
# default: a mistake in the fixture must not spill test events into the
# stream a real comms consumer reads.
TEST_STREAM = "test:comms:events:t63"


@pytest.fixture
async def relay_redis():
    """A client to the test Redis plus a throwaway stream, cleaned after.

    decode_responses=False mirrors the relay's own client, so the entries
    read back here have the same shape the comms consumer sees.
    """
    redis = aioredis.from_url(settings.redis_url, decode_responses=False)
    try:
        with patch.object(settings, "comms_events_stream", TEST_STREAM):
            yield redis, TEST_STREAM
    finally:
        await redis.delete(TEST_STREAM)
        await redis.aclose()


async def _emit(session: AsyncSession, tag: str) -> OutboxEvent:
    """One pending row, tagged so this suite can find it again."""
    return await emit_event(
        session,
        EVENT_GROUP_CHANGED,
        {
            "group_key": "relay-test",
            "recipient_id": f"{SYNTH}{tag}",
            "member": True,
        },
    )


async def _synth_rows(session: AsyncSession) -> list[OutboxEvent]:
    """This suite's rows, in id order."""
    result = await session.execute(select(OutboxEvent).order_by(OutboxEvent.id))
    return [
        row
        for row in result.scalars().all()
        if str(row.payload.get("recipient_id", "")).startswith(SYNTH)
    ]


async def _rows_by_id(session: AsyncSession, ids: list[int]) -> dict[int, OutboxEvent]:
    """Rows read back by primary key, keyed by id.

    Deliberately NOT _synth_rows: that helper recognises this suite's
    rows by the SYNTH prefix inside payload, which is fine everywhere
    payload is inert -- and wrong in the redaction test, whose whole
    subject is payload being overwritten. A redacted row stops looking
    like ours the moment the code under test succeeds, so the identity
    marker cannot live in the field being tested.
    """
    result = await session.execute(select(OutboxEvent).where(OutboxEvent.id.in_(ids)))
    return {row.id: row for row in result.scalars().all()}


def _recipients(entries: list) -> list[str]:
    """recipient_id of every stream entry, in stream order."""
    return [json.loads(fields[b"data"])["recipient_id"] for _, fields in entries]


# ---------------------------------------------------------------------------
# 1. The happy path: order, marking, and a harmless repeat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publishes_in_id_order_and_marks_published(
    db_session: AsyncSession, relay_redis
) -> None:
    """Two rows reach the stream in id order and both are marked."""
    redis, stream = relay_redis
    first = await _emit(db_session, "order-a")
    second = await _emit(db_session, "order-b")
    assert first.id < second.id, "emit order must be id order"

    assert await relay_pending_batch(redis, session=db_session) == (2, 0)

    entries = await redis.xrange(stream)
    assert _recipients(entries) == [f"{SYNTH}order-a", f"{SYNTH}order-b"]
    assert entries[0][1][b"event"] == EVENT_GROUP_CHANGED.encode()

    # A stream with no consumer group at all: the comms consumer creates
    # the group itself with MKSTREAM when it first starts, so publishing
    # ahead of any reader loses nothing.
    assert await redis.xinfo_groups(stream) == []

    rows = await _synth_rows(db_session)
    assert [row.published_at is not None for row in rows] == [True, True]
    assert [row.attempts for row in rows] == [0, 0]

    # Repeat axis: published rows have left the scan predicate.
    assert await relay_pending_batch(redis, session=db_session) == (0, 0)

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 2. Emptiness: nothing pending means nothing spoken to Redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_outbox_issues_no_xadd(
    db_session: AsyncSession, relay_redis
) -> None:
    """An idle relay must be silent, not merely harmless.

    The counts are exact on purpose: a row committed by some future
    emitter would fail this test loudly instead of quietly making it
    measure something else.
    """
    redis, stream = relay_redis
    calls: list[tuple] = []

    async def _spy(*args, **kwargs):
        calls.append(args)

    with patch.object(redis, "xadd", side_effect=_spy):
        assert await relay_pending_batch(redis, session=db_session) == (0, 0)

    assert calls == []
    assert await redis.xlen(stream) == 0

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 3. Poison row: charged, backed off, and NOT blocking the pipe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poison_row_is_charged_and_does_not_block_the_batch(
    db_session: AsyncSession, relay_redis
) -> None:
    """Per-event failure, not per-batch: the other rows still publish."""
    redis, stream = relay_redis
    poison = await _emit(db_session, "poison")
    await _emit(db_session, "sound-a")
    await _emit(db_session, "sound-b")
    poison_id = poison.id

    real_xadd = redis.xadd

    async def _poisoned(stream_name, fields, *args, **kwargs):
        if json.loads(fields["data"])["recipient_id"] == f"{SYNTH}poison":
            raise RuntimeError("this one event is malformed for the wire")
        return await real_xadd(stream_name, fields, *args, **kwargs)

    before = datetime.now(UTC)
    with patch.object(redis, "xadd", side_effect=_poisoned):
        assert await relay_pending_batch(redis, session=db_session) == (2, 1)

    entries = await redis.xrange(stream)
    assert _recipients(entries) == [f"{SYNTH}sound-a", f"{SYNTH}sound-b"]

    rows = await _synth_rows(db_session)
    bad = next(row for row in rows if row.id == poison_id)
    good = [row for row in rows if row.id != poison_id]

    assert bad.attempts == 1
    assert bad.published_at is None, "a failed row is never marked shipped"
    assert bad.dead_lettered_at is None, "one failure is not the ceiling"
    assert bad.next_attempt_at is not None
    assert bad.next_attempt_at > before, "the retry is deferred, not immediate"

    assert all(row.published_at is not None for row in good)
    assert all(row.attempts == 0 for row in good)

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 4-5. Infrastructure: the pass stops and NOTHING is charged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_failure_charges_nothing_and_the_row_ships_later(
    db_session: AsyncSession, relay_redis
) -> None:
    """An outage is not the rows' fault.

    Charging attempts here would let one long outage walk healthy rows
    to the dead-letter ceiling without a single one of them ever having
    been offered to a working Redis.
    """
    redis, stream = relay_redis
    await _emit(db_session, "infra-a")
    await _emit(db_session, "infra-b")

    with patch.object(redis, "xadd", side_effect=RedisConnectionError("down")):
        assert await relay_pending_batch(redis, session=db_session) == (0, 0)

    rows = await _synth_rows(db_session)
    assert len(rows) == 2
    assert all(row.attempts == 0 for row in rows)
    assert all(row.published_at is None for row in rows)
    assert all(row.next_attempt_at is None for row in rows), "no backoff for infra"
    assert await redis.xlen(stream) == 0, "the pass aborted at the first row"

    # Redis is back: the next tick ships both, still unmarked by the outage.
    assert await relay_pending_batch(redis, session=db_session) == (2, 0)
    assert _recipients(await redis.xrange(stream)) == [
        f"{SYNTH}infra-a",
        f"{SYNTH}infra-b",
    ]

    await db_session.rollback()


@pytest.mark.asyncio
async def test_redis_refusal_is_infrastructure_not_poison(
    db_session: AsyncSession, relay_redis
) -> None:
    """ResponseError means Redis answered and refused -- OOM, READONLY,
    an ACL rejection. The event is not at fault, so it is not charged.
    """
    redis, _stream = relay_redis
    await _emit(db_session, "refused")

    with patch.object(
        redis, "xadd", side_effect=RedisResponseError("OOM command not allowed")
    ):
        assert await relay_pending_batch(redis, session=db_session) == (0, 0)

    row = (await _synth_rows(db_session))[0]
    assert row.attempts == 0
    assert row.published_at is None
    assert row.next_attempt_at is None
    assert row.dead_lettered_at is None

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 6. The ceiling: marked dead once, published_at stays empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ceiling_marks_dead_once_and_leaves_published_at_empty(
    db_session: AsyncSession, relay_redis
) -> None:
    """At the attempts limit the row leaves the pipe -- without ever
    pretending it was shipped.

    published_at is the load-bearing assertion: a dead row that carried a
    publication timestamp would be indistinguishable from a delivered
    one, and the redaction pass would then destroy the payload of a
    message that was never sent.
    """
    redis, stream = relay_redis
    row = await _emit(db_session, "doomed")
    row_id = row.id

    with (
        patch.object(settings, "comms_relay_max_attempts", 2),
        patch.object(redis, "xadd", side_effect=RuntimeError("always bad")),
    ):
        # Pass 1: charged and deferred, still alive.
        assert await relay_pending_batch(redis, session=db_session) == (0, 1)
        alive = (await _synth_rows(db_session))[0]
        assert alive.attempts == 1
        assert alive.dead_lettered_at is None

        # Lapse the backoff: this test is about the ceiling, not about
        # waiting for the clock.
        alive.next_attempt_at = None
        await db_session.flush()

        # Pass 2: the limit is reached.
        assert await relay_pending_batch(redis, session=db_session) == (0, 1)
        dead = (await _synth_rows(db_session))[0]
        assert dead.id == row_id
        assert dead.attempts == 2
        assert dead.dead_lettered_at is not None
        assert dead.published_at is None, "dead means never shipped, not shipped"

        # Pass 3: the dead row is out of the select, so the loud ERROR
        # it logged on the way out can never repeat.
        assert await relay_pending_batch(redis, session=db_session) == (0, 0)

    assert await redis.xlen(stream) == 0

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 7. Redaction: only what was shipped, only past the window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redaction_touches_only_rows_shipped_past_the_window(
    db_session: AsyncSession,
) -> None:
    """Four rows, one victim.

    A pending row is spared at any age because for a row that never
    shipped the payload is the only copy of what still has to be
    delivered. A dead-lettered row is spared by the same rule (it keeps
    published_at NULL by design) -- that retention is the ceiling stated
    at the dead-lettering branch of the relay, asserted here so it stays
    a deliberate state rather than a surprise.
    """
    old = datetime.now(UTC) - timedelta(days=PAYLOAD_RETENTION_DAYS + 1)
    fresh = datetime.now(UTC) - timedelta(days=1)

    shipped_old = await _emit(db_session, "red-shipped-old")
    shipped_old.published_at = old
    shipped_fresh = await _emit(db_session, "red-shipped-fresh")
    shipped_fresh.published_at = fresh
    pending_old = await _emit(db_session, "red-pending-old")
    dead_old = await _emit(db_session, "red-dead-old")
    dead_old.attempts = settings.comms_relay_max_attempts
    dead_old.dead_lettered_at = old
    await db_session.flush()

    victim_id = shipped_old.id
    spared_ids = {shipped_fresh.id, pending_old.id, dead_old.id}

    assert await redact_published_payloads(session=db_session) == 1

    # The bulk UPDATE does not synchronise the identity map on purpose,
    # so read the rows back rather than trusting the objects in hand --
    # by id, for the reason spelled out in _rows_by_id.
    db_session.expire_all()
    rows = await _rows_by_id(db_session, [victim_id, *sorted(spared_ids)])
    assert set(rows) == {victim_id, *spared_ids}

    assert rows[victim_id].payload == REDACTED_PAYLOAD
    assert rows[victim_id].published_at is not None, "the skeleton is kept"
    assert rows[victim_id].event_type == EVENT_GROUP_CHANGED, "and so is the type"
    for spared_id in spared_ids:
        spared = rows[spared_id]
        assert spared.payload != REDACTED_PAYLOAD
        assert spared.payload["recipient_id"].startswith(SYNTH)

    # Repeat axis: a redacted row no longer matches the predicate, which
    # is the same fact as it having left the partial index.
    assert await redact_published_payloads(session=db_session) == 0

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 8-9. The wire envelope, and the connection the loop is given
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_envelope_matches_the_contract_and_a_bare_payload_still_ships(
    db_session: AsyncSession, relay_redis
) -> None:
    """The relay is transport, not a validator.

    A payload that carries nothing but its version is short of every
    field the comms schema for this event requires. It still ships: per-
    type schemas live in the comms consumer, on the other side of a
    service boundary, and a relay that second-guessed them would be
    holding a mirror of somebody else's code.
    """
    redis, stream = relay_redis
    bare = await emit_event(db_session, EVENT_GROUP_CHANGED, {})

    envelope = build_envelope(bare)
    assert set(envelope) == {"event", "data"}
    assert envelope["event"] == EVENT_GROUP_CHANGED
    assert json.loads(envelope["data"]) == {"v": 1}

    assert await relay_pending_batch(redis, session=db_session) == (1, 0)
    entries = await redis.xrange(stream)
    assert len(entries) == 1
    assert json.loads(entries[0][1][b"data"]) == {"v": 1}
    assert entries[0][1][b"event"] == EVENT_GROUP_CHANGED.encode()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_relay_connection_carries_its_socket_timeouts() -> None:
    """A hung TCP connection must surface as a timeout, not as a stalled
    loop -- which only holds if the settings actually reach the client.
    """
    captured: dict = {}

    def _fake_from_url(url, **kwargs):
        captured.update(kwargs, url=url)
        return object()

    with patch.object(aioredis, "from_url", side_effect=_fake_from_url):
        create_relay_redis()

    assert captured["url"] == settings.comms_redis_url
    assert captured["decode_responses"] is False
    assert (
        captured["socket_connect_timeout"]
        == settings.comms_relay_socket_connect_timeout_seconds
    )
    assert captured["socket_timeout"] == settings.comms_relay_socket_timeout_seconds
