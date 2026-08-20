# =============================================================================
# AIVIS.ONE Backend -- Transactional Outbox tests (T-62)
# =============================================================================
#
# Tests cover:
#   1:  known event type accepted, row written, "v" stamped
#   2:  unknown event type rejected, known ones named
#   3:  caller-supplied "v" rejected
#   4:  non-JSON values rejected (datetime / Decimal / UUID / set)
#   5:  non-JSON value nested in a list or object rejected, path named
#   6:  non-string and empty dict keys rejected
#   7:  empty data accepted -- see the docstring, this is not a gap
#   8:  data missing the fields a given event type needs is accepted --
#       also not a gap, see the docstring
#   9:  no commit: the row is invisible from a second session until the
#       caller commits, and gone entirely if the caller rolls back
#   10: two emits in one session get strictly increasing ids
#   11: default values of the three nullable lifecycle columns
#
# NO USERS, NO HTTP. Every test here writes to outbox_events through
# db_session and reads it back; nothing in this file touches the auth
# layer, so no telegram_id and no e-mail prefix are needed and none are
# claimed.
#
# WHAT THIS FILE DELIBERATELY DOES NOT TEST: that comms accepts what we
# emit. emit_event knows the envelope contract (the set of event names,
# the version field, JSON discipline) and nothing about per-type
# schemas -- those live in the comms consumer, on the other side of a
# service boundary, and asserting them here would be asserting a mirror
# of somebody else's code.
# =============================================================================

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.core.events.models import OutboxEvent
from app.core.events.service import (
    EVENT_GROUP_CHANGED,
    EVENT_NOTIFICATION_REQUEST,
    EVENT_REMINDER_CANCEL,
    EVENT_USER_UPSERTED,
    KNOWN_EVENT_TYPES,
    SCHEMA_VERSION,
    emit_event,
)

# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_event_writes_row_and_stamps_version(
    db_session: AsyncSession,
) -> None:
    """A known type is accepted; the version is added, not taken."""
    event = await emit_event(
        db_session,
        EVENT_USER_UPSERTED,
        {"id": str(uuid4()), "email": "a@example.test", "active": True},
    )

    assert event.id is not None, "flush must assign the BIGSERIAL id"
    assert event.event_type == EVENT_USER_UPSERTED
    assert event.payload["v"] == SCHEMA_VERSION
    assert event.payload["active"] is True

    await db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    [
        EVENT_NOTIFICATION_REQUEST,
        EVENT_USER_UPSERTED,
        EVENT_GROUP_CHANGED,
        EVENT_REMINDER_CANCEL,
    ],
)
async def test_every_contract_event_type_is_accepted(
    db_session: AsyncSession, event_type: str
) -> None:
    """All four names of the frozen wire contract are emittable.

    reminder_cancel is included although no aivis code emits it: the
    set describes what the wire accepts, not what this product happens
    to send today. A test that skipped it would quietly turn the
    contract into an inventory of our current intentions.
    """
    event = await emit_event(db_session, event_type, {"probe": 1})
    assert event.event_type == event_type
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 2-3. Rejections on the envelope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_event_type_is_rejected_and_names_the_known(
    db_session: AsyncSession,
) -> None:
    """The error has to teach: an unknown name lists the known ones."""
    with pytest.raises(ValueError) as exc:
        await emit_event(db_session, "booking_confirmed", {"x": 1})

    message = str(exc.value)
    assert "booking_confirmed" in message
    for known in KNOWN_EVENT_TYPES:
        assert known in message


@pytest.mark.asyncio
async def test_caller_supplied_version_is_rejected(
    db_session: AsyncSession,
) -> None:
    """'v' is stamped here, never accepted.

    The comms consumer validates the version on every event and
    strictly as an int, dead-lettering anything else. Letting a caller
    set it would move that failure across a service boundary, where it
    surfaces as somebody else's DLQ entry hours later.
    """
    with pytest.raises(ValueError, match="'v'"):
        await emit_event(db_session, EVENT_USER_UPSERTED, {"v": 2, "id": "x"})


# ---------------------------------------------------------------------------
# 4-6. JSON discipline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("datetime", datetime.now(UTC)),
        ("Decimal", Decimal("1.50")),
        ("UUID", uuid4()),
        ("set", {1, 2}),
    ],
)
async def test_non_json_value_is_rejected(
    db_session: AsyncSession, label: str, value: object
) -> None:
    """JSONB would store these happily; the wire would not survive them.

    Every one of these is a plausible accident at an emit site -- a raw
    model attribute passed straight through. Caught here, it is a
    ValueError in the emitting test; not caught, it is either a crash
    in the relay's json.dumps or a dead letter in comms.
    """
    with pytest.raises(ValueError) as exc:
        await emit_event(db_session, EVENT_USER_UPSERTED, {"field": value})
    assert "data.field" in str(exc.value)


@pytest.mark.asyncio
async def test_non_json_value_nested_in_a_tree_is_rejected_with_its_path(
    db_session: AsyncSession,
) -> None:
    """The path in the error is the point: it says WHICH leaf."""
    with pytest.raises(ValueError) as exc:
        await emit_event(
            db_session,
            EVENT_NOTIFICATION_REQUEST,
            {"params": {"items": [1, {"when": datetime.now(UTC)}]}},
        )
    assert "data.params.items[1].when" in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_key", [1, "", None])
async def test_non_string_or_empty_object_key_is_rejected(
    db_session: AsyncSession, bad_key: object
) -> None:
    """JSON object keys are non-empty strings, and nothing else."""
    with pytest.raises(ValueError, match="non-empty string"):
        await emit_event(db_session, EVENT_USER_UPSERTED, {"nested": {bad_key: 1}})


# ---------------------------------------------------------------------------
# 7-8. What is deliberately ACCEPTED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_data_is_accepted(db_session: AsyncSession) -> None:
    """An empty document is legal JSON and emit_event takes it.

    Asserted rather than left untested so the next reader does not read
    the absence of a test as a prohibition. The payload of such a row is
    the version field alone -- the comms consumer is what rejects it,
    per its own per-type schema, and that rejection is not this
    function's job to duplicate.
    """
    event = await emit_event(db_session, EVENT_USER_UPSERTED, {})
    assert event.payload == {"v": SCHEMA_VERSION}
    await db_session.rollback()


@pytest.mark.asyncio
async def test_data_missing_its_type_fields_is_accepted(
    db_session: AsyncSession,
) -> None:
    """emit_event validates the envelope, not the per-type schema.

    notification_request needs a recipient, a title and a body on the
    comms side; none of them is required here. The boundary is
    deliberate: mirroring another service's schemas in this module
    would mean two copies of them, and the copy that drifts is always
    the one that is not the source.
    """
    event = await emit_event(
        db_session, EVENT_NOTIFICATION_REQUEST, {"unrelated": "field"}
    )
    assert event.payload == {"v": SCHEMA_VERSION, "unrelated": "field"}
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 9. The whole point: no commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_row_is_invisible_to_another_session_until_caller_commits(
    db_session: AsyncSession,
) -> None:
    """emit_event flushes; it does not commit.

    This is the property the outbox pattern is built on: the event and
    the domain change share one transaction, so they become visible
    together or not at all. A commit inside emit_event would publish
    the event while the domain change could still roll back.

    Checked from a SECOND session on purpose -- the caller's own
    session sees its uncommitted row, so reading it back there would
    prove nothing.
    """
    marker = f"invisible-{uuid4()}"
    event = await emit_event(db_session, EVENT_USER_UPSERTED, {"m": marker})
    event_id = event.id

    factory = get_session_factory()
    async with factory() as other:
        found = await other.scalar(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        assert found is None, (
            "the row was visible from another session before the caller "
            "committed -- emit_event committed, and the outbox guarantee "
            "is gone"
        )

    await db_session.commit()

    async with factory() as other:
        found = await other.scalar(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        assert found is not None, "the row must appear once the caller commits"
        assert found.payload["m"] == marker

    # Leave nothing behind: this is the one test here that commits.
    async with factory() as cleanup:
        row = await cleanup.get(OutboxEvent, event_id)
        if row is not None:
            await cleanup.delete(row)
            await cleanup.commit()


@pytest.mark.asyncio
async def test_row_disappears_when_the_caller_rolls_back(
    db_session: AsyncSession,
) -> None:
    """The caller's rollback is the event's rollback."""
    event = await emit_event(db_session, EVENT_USER_UPSERTED, {"m": "gone"})
    event_id = event.id

    await db_session.rollback()

    factory = get_session_factory()
    async with factory() as other:
        found = await other.scalar(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        assert found is None


# ---------------------------------------------------------------------------
# 10. Emission order is publication order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ids_increase_within_one_session(
    db_session: AsyncSession,
) -> None:
    """Two events emitted in order get ids in that order.

    The relay publishes strictly by id, so this is not a property of
    the column -- it is the ordering guarantee the whole design rests
    on, and it holds because emit_event flushes rather than deferring
    the insert to commit time.
    """
    first = await emit_event(db_session, EVENT_USER_UPSERTED, {"n": 1})
    second = await emit_event(db_session, EVENT_USER_UPSERTED, {"n": 2})

    assert second.id > first.id

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 11. Column defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifecycle_columns_start_empty(
    db_session: AsyncSession,
) -> None:
    """A fresh row is pending, never attempted, never dead-lettered.

    published_at NULL is the relay's scan predicate; next_attempt_at
    NULL means "may be picked up immediately", which is why no backfill
    is ever needed for rows created before a backoff existed;
    dead_lettered_at NULL means alive. attempts starts at 0 in the
    database, not just in Python -- the server_default is what a row
    inserted by anything other than this model would get.
    """
    event = await emit_event(db_session, EVENT_GROUP_CHANGED, {"g": "staff"})
    await db_session.refresh(event)

    assert event.published_at is None
    assert event.next_attempt_at is None
    assert event.dead_lettered_at is None
    assert event.attempts == 0
    assert event.created_at is not None

    await db_session.rollback()
