# =============================================================================
# AIVIS.ONE Backend -- support operators: the group and the mute (H40)
# =============================================================================
#
# Who an operator is, in comms, is declared in ONE place
# (service.emit_support_membership): the section roster, the group
# `support_operators` (where "every operator" signals go), and -- for a new
# operator -- the mute of comms' own msg.support_message ping, whose
# category `staff_messages` the product turns off in the operator's comms
# preferences (owner ruling; support/mute.py says why). Pinned here:
#
#   1. the roster and the group move together, with the same `member`;
#   2. becoming an operator queues ONE mute, in the same transaction;
#      leaving touches nothing; no comms address writes nothing;
#   3. the step carries a mute out (PATCH, the row gone on 200) and keeps
#      it, counted, when comms cannot take it yet -- a recipient not there
#      yet, comms down -- and says so loudly when it is a defect or stuck;
#   4. the backfills (0061, 0062) write one row per active profile;
#   5. after the mute, comms' ping reaches the operator no more, the H40
#      signal does, and the bell's count is the bell's rows.
#
# The MUTE RULE ITSELF is comms' (a muted category creates no delivery);
# the fake applies it, and what is checked is the product's side -- that
# the mute was set. comms is the fake of tests/support_fake.py.
# =============================================================================

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.core.comms import CommsRejectedError
from app.core.events.models import OutboxEvent
from app.core.events.service import (
    EVENT_GROUP_CHANGED,
    EVENT_SECTION_MEMBERSHIP_CHANGED,
)
from app.modules.support import mute
from app.modules.support.models import SupportOperatorMute
from app.modules.support.service import emit_support_membership
from app.modules.users.models import User
from tests.helpers import auth_headers, create_admin_user, register_user
from tests.support_fake import FakeComms, install


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> FakeComms:
    return install(monkeypatch)


@pytest.fixture(autouse=True)
async def _clean(db_session: AsyncSession) -> Any:
    await db_session.execute(delete(SupportOperatorMute))
    await db_session.commit()
    yield
    await db_session.execute(delete(SupportOperatorMute))
    await db_session.commit()


async def _person(client: AsyncClient) -> UUID:
    return UUID((await register_user(client))["user"]["id"])


async def _mutes(session: AsyncSession) -> dict[UUID, SupportOperatorMute]:
    session.expire_all()
    rows = (await session.execute(select(SupportOperatorMute))).scalars()
    return {row.user_id: row for row in rows}


async def _events(session: AsyncSession, kind: str, user_id: UUID) -> list[dict]:
    field = (
        "operator_id" if kind == EVENT_SECTION_MEMBERSHIP_CHANGED else "recipient_id"
    )
    rows = (
        await session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type == kind,
                OutboxEvent.payload[field].astext == str(user_id),
            )
            .order_by(OutboxEvent.id)
        )
    ).scalars()
    return [r.payload for r in rows]


# ---------------------------------------------------------------------------
# 1-2. One declaration, three effects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promotion_declares_roster_and_group_and_queues_one_mute(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    _admin, admin_token = await create_admin_user(client, db_session)
    target = await _person(client)
    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": str(target)},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code in (200, 201), resp.text

    roster = await _events(db_session, EVENT_SECTION_MEMBERSHIP_CHANGED, target)
    group = await _events(db_session, EVENT_GROUP_CHANGED, target)
    assert [e["member"] for e in roster] == [True]
    assert [(e["group_key"], e["member"]) for e in group] == [
        ("support_operators", True)
    ]
    assert list(await _mutes(db_session)) == [target]


@pytest.mark.asyncio
async def test_a_repeated_membership_is_one_mute(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    target = await _person(client)
    for _ in range(2):
        await emit_support_membership(db_session, user_id=target)
    await db_session.commit()
    rows = await _mutes(db_session)
    assert list(rows) == [target]
    assert rows[target].attempts == 0


@pytest.mark.asyncio
async def test_leaving_moves_both_declarations_and_touches_no_mute(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    target = await _person(client)
    await emit_support_membership(db_session, user_id=target, member=False)
    await db_session.commit()
    assert [
        e["member"] for e in await _events(db_session, EVENT_GROUP_CHANGED, target)
    ] == [False]
    assert [
        e["member"]
        for e in await _events(db_session, EVENT_SECTION_MEMBERSHIP_CHANGED, target)
    ] == [False]
    assert await _mutes(db_session) == {}


@pytest.mark.asyncio
async def test_no_comms_address_writes_no_mute_either(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    target = await _person(client)
    monkeypatch.setattr(settings, "comms_api_url", "")
    await emit_support_membership(db_session, user_id=target)
    await db_session.commit()
    assert await _mutes(db_session) == {}
    assert await _events(db_session, EVENT_GROUP_CHANGED, target) == []


# ---------------------------------------------------------------------------
# 3. Carrying the mute out
# ---------------------------------------------------------------------------


async def _queue(session: AsyncSession, *user_ids: UUID, attempts: int = 0) -> None:
    for user_id in user_ids:
        await session.execute(
            text(
                "INSERT INTO support_operator_mutes (user_id, queued_at, attempts) "
                "VALUES (:u, now(), :a)"
            ),
            {"u": user_id, "a": attempts},
        )
    await session.commit()


@pytest.mark.asyncio
async def test_a_mute_comms_takes_is_done_and_gone(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    target = await _person(client)
    await _queue(db_session, target)
    assert await mute.apply_operator_mutes() == 1
    [patch] = comms.calls_to("PATCH", f"/recipients/{target}/preferences")
    assert patch["json"] == {"categories": {"staff_messages": False}}
    assert comms.preferences[str(target)]["staff_messages"] is False
    assert comms.preferences[str(target)]["support_messages"] is True  # only that one
    assert await _mutes(db_session) == {}
    # The pair of "gone": a second step has nothing to do.
    assert await mute.apply_operator_mutes() == 0
    assert len(comms.calls_to("PATCH", "/preferences")) == 1


@pytest.mark.asyncio
async def test_a_recipient_comms_does_not_have_yet_waits_and_is_counted(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    target = await _person(client)
    comms.recipients.discard(str(target))
    await _queue(db_session, target)
    with capture_logs() as logs:
        assert await mute.apply_operator_mutes() == 0
    row = (await _mutes(db_session))[target]
    assert (row.attempts, row.last_error_at is not None) == (1, True)
    assert not [e for e in logs if e["log_level"] in ("error", "warning")]
    # Its user_upserted arrives: the next step mutes.
    comms.know(target)
    assert await mute.apply_operator_mutes() == 1
    assert await _mutes(db_session) == {}


@pytest.mark.asyncio
async def test_comms_down_tries_every_row_once_per_step(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    people = [await _person(client) for _ in range(3)]
    await _queue(db_session, *people)
    comms.down = True
    assert await mute.apply_operator_mutes() == 0
    assert len(comms.calls_to("PATCH", "/preferences")) == 3
    assert {r.attempts for r in (await _mutes(db_session)).values()} == {1}


@pytest.mark.asyncio
async def test_a_refusal_that_is_a_defect_is_an_error_at_once(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    target = await _person(client)
    await _queue(db_session, target)
    comms.fail[("PATCH", "/preferences")] = CommsRejectedError(
        status_code=422, error_class="validation"
    )
    with capture_logs() as logs:
        await mute.apply_operator_mutes()
    errors = [e for e in logs if e["event"] == "support_operator_mute_refused"]
    assert [(e["log_level"], e["refusal"], e["user_id"]) for e in errors] == [
        ("error", "validation", str(target))
    ]
    assert target in await _mutes(db_session)  # kept: the fix carries it out


@pytest.mark.asyncio
async def test_a_stuck_mute_is_a_warning_on_every_failure_from_the_threshold(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    early, stuck = await _person(client), await _person(client)
    await _queue(db_session, early, attempts=0)
    await _queue(db_session, stuck, attempts=mute.STUCK_AFTER_ATTEMPTS - 1)
    comms.down = True
    for _ in range(2):
        with capture_logs() as logs:
            await mute.apply_operator_mutes()
        warned = [e for e in logs if e["event"] == "support_operator_mute_stuck"]
        assert [e["user_id"] for e in warned] == [str(stuck)]
        assert warned[0]["refusal"] == "comms_unavailable"
    rows = await _mutes(db_session)
    assert rows[stuck].attempts == mute.STUCK_AFTER_ATTEMPTS + 1
    assert rows[early].attempts == 2


@pytest.mark.asyncio
async def test_a_deleted_person_leaves_no_mute_behind(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    target = await _person(client)
    await _queue(db_session, target)
    await db_session.execute(delete(User).where(User.id == target))
    await db_session.commit()
    assert await _mutes(db_session) == {}


# ---------------------------------------------------------------------------
# 4. The backfills
# ---------------------------------------------------------------------------


def _migration(name: str) -> Any:
    import importlib.util
    from pathlib import Path

    path = next(Path(__file__).parents[1].glob(f"migrations/versions/*{name}*.py"))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_the_mute_backfill_is_one_row_per_active_profile(
    db_session: AsyncSession,
) -> None:
    active = set(
        (
            await db_session.execute(
                text("SELECT user_id FROM staff_profiles WHERE is_active = true")
            )
        ).scalars()
    )
    assert active, "the pair: there are staff to backfill"
    statement = _migration("0062_support_operator_mutes").BACKFILL_SQL
    for _ in range(2):  # a replay adds nothing
        await db_session.execute(text(statement))
    await db_session.commit()
    assert set(await _mutes(db_session)) == active


@pytest.mark.asyncio
async def test_the_group_backfill_declares_each_active_profile(
    db_session: AsyncSession,
) -> None:
    from unittest.mock import patch

    active = set(
        (
            await db_session.execute(
                text("SELECT user_id FROM staff_profiles WHERE is_active = true")
            )
        ).scalars()
    )
    source = _migration("0061_support_operators_group")
    connection = await db_session.connection()

    def _run(sync_conn: Any) -> None:
        with patch.object(source.op, "get_bind", return_value=sync_conn):
            source.upgrade()

    marker = (
        await db_session.execute(text("SELECT coalesce(max(id), 0) FROM outbox_events"))
    ).scalar_one()
    await connection.run_sync(_run)
    rows = (
        (
            await db_session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.id > marker,
                    OutboxEvent.event_type == EVENT_GROUP_CHANGED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert {UUID(r.payload["recipient_id"]) for r in rows} == active
    assert {
        (r.payload["group_key"], r.payload["member"], r.payload["v"]) for r in rows
    } == {("support_operators", True, 1)}
    await db_session.execute(
        delete(OutboxEvent).where(OutboxEvent.id.in_([r.id for r in rows]))
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# 5. What the operator gets, and the bell
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_after_the_mute_the_bell_counts_what_it_shows(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    body = await register_user(client)
    operator = UUID(body["user"]["id"])
    headers = auth_headers(body["session_token"])
    await emit_support_membership(db_session, user_id=operator)
    await db_session.commit()
    assert await mute.apply_operator_mutes() == 1

    # A person writes: comms would ping the operator with its own type,
    # and the product sends its signal.
    assert (
        comms.deliver(
            type="msg.support_message", category="staff_messages", recipient=operator
        )
        is False
    )
    assert (
        comms.deliver(
            type="support.message_received", category=None, recipient=operator
        )
        is True
    )

    page = (await client.get("/api/v1/notifications", headers=headers)).json()
    count = (
        await client.get("/api/v1/notifications/unread-count", headers=headers)
    ).json()
    assert [item["type"] for item in page["items"]] == ["support.message_received"]
    assert count["unread"] == len(page["items"]) == page["unread"] == 1


@pytest.mark.asyncio
async def test_without_the_mute_the_ping_would_double(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    """The other half: the fake's rule is not what makes the bell agree --
    before the mute, comms' ping lands beside the signal."""
    body = await register_user(client)
    operator = UUID(body["user"]["id"])
    headers = auth_headers(body["session_token"])
    comms.deliver(
        type="msg.support_message", category="staff_messages", recipient=operator
    )
    comms.deliver(type="support.message_received", category=None, recipient=operator)
    page = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert sorted(i["type"] for i in page["items"]) == [
        "msg.support_message",
        "support.message_received",
    ]


@pytest.mark.asyncio
async def test_the_mute_is_never_re_applied_once_taken(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    """An operator who turns the category back on keeps that choice: the
    product mutes once, at the membership, and never again by itself."""
    target = await _person(client)
    await _queue(db_session, target)
    await mute.apply_operator_mutes()
    comms.preferences[str(target)]["staff_messages"] = True  # their own choice
    await mute.apply_operator_mutes()
    assert comms.preferences[str(target)]["staff_messages"] is True
    assert len(comms.calls_to("PATCH", "/preferences")) == 1
