# =============================================================================
# AIVIS.ONE Backend -- Support, the operator's side (T-66, H40 tickets)
# =============================================================================
#
# Rewritten for H40. The T-66 suite pinned comms' own queue, scoped by an
# `is_supervisor` the product stamped; both are gone (owner ruling): the
# list is the product's table and EVERY operator sees EVERY ticket. What
# T-66 pinned and still holds is kept on the new routes:
#
#   1. only an active staff member gets through at all;
#   2. no actor name is readable from a request; `operator` reaching comms
#      is the session's;
#   3. taking is idempotent for its holder and a conflict for anyone else;
#   4. replying without taking is refused in a way that says what to do;
#   5. comms being down is an answer.
#
# What H40 adds: the list's filters and cursor, the card, the handover
# (assign / release) with its signals, the four closing statuses with the
# compare-and-set, the way back to work (spam only within its retention),
# the person's history read-only, the signal on every message of a person.
#
# comms is the stateful fake of tests/support_fake.py; the operators are
# put on its roster by hand (create_staff_user writes the profile directly,
# not through the membership emitter).
# =============================================================================

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.models import OutboxEvent
from app.modules.staff.models import StaffProfile
from app.modules.support.models import SupportThread, SupportTicket
from tests.helpers import auth_headers, create_staff_user, register_user
from tests.support_fake import FakeComms, install

_PERSON = "/api/v1/support"
_STAFF = "/api/v1/staff/support"


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> FakeComms:
    return install(monkeypatch)


class Op:
    def __init__(self, user: Any, token: str) -> None:
        self.id = user.id
        self.headers = auth_headers(token)


async def _operator(client: AsyncClient, session: AsyncSession, comms: FakeComms) -> Op:
    user, token = await create_staff_user(client, session)
    comms.serve(user.id)
    return Op(user, token)


async def _person(client: AsyncClient) -> tuple[dict[str, str], UUID]:
    body = await register_user(client)
    return auth_headers(body["session_token"]), UUID(body["user"]["id"])


def _key(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid4())}


async def _ticket(
    client: AsyncClient,
    *,
    topic: str = "payments",
    body: str = "help",
    person: tuple[dict[str, str], UUID] | None = None,
) -> tuple[str, dict[str, str], UUID]:
    """A ticket opened through the form: (its id, the person's headers, id)."""
    headers, user_id = person or await _person(client)
    resp = await client.post(
        f"{_PERSON}/tickets",
        json={"topic": topic, "body": body},
        headers=_key(headers),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ticket"]["id"], headers, user_id


async def _row(session: AsyncSession, thread_id: str) -> SupportTicket:
    session.expire_all()
    return (
        await session.execute(
            select(SupportTicket)
            .join(SupportThread, SupportThread.id == SupportTicket.support_thread_id)
            .where(SupportThread.comms_thread_id == UUID(thread_id))
        )
    ).scalar_one()


async def _set(session: AsyncSession, thread_id: str, **values: Any) -> None:
    row = await _row(session, thread_id)
    await session.execute(
        update(SupportTicket)
        .where(SupportTicket.support_thread_id == row.support_thread_id)
        .values(**values)
    )
    await session.commit()


async def _signals(session: AsyncSession, thread_id: str) -> list[dict[str, Any]]:
    session.expire_all()
    rows = (
        await session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.payload["type"].astext.like("support.%"),
                OutboxEvent.payload["action_data"]["params"]["id"].astext == thread_id,
            )
            .order_by(OutboxEvent.id)
        )
    ).scalars()
    return [r.payload for r in rows]


async def _post(client: AsyncClient, op: Op, path: str, body: Any = None) -> Any:
    return await client.post(f"{_STAFF}{path}", json=body, headers=op.headers)


@pytest.fixture(autouse=True)
async def _no_signal_residue(db_session: AsyncSession) -> Any:
    yield
    await db_session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.payload["type"].astext.like("support.%")
            | OutboxEvent.payload["idempotency_key"].astext.like(
                "aivis:llm-support-tr:%"
            )
        )
    )
    await db_session.commit()


# ---------------------------------------------------------------------------
# 1-2. Who is let in, and who reaches comms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_ordinary_user_is_not_an_operator(
    client: AsyncClient, comms: FakeComms
) -> None:
    headers, _ = await _person(client)
    for path in ("/tickets", "/operators"):
        resp = await client.get(f"{_STAFF}{path}", headers=headers)
        assert resp.status_code == 403, resp.text
    assert comms.calls == []


@pytest.mark.asyncio
async def test_a_deactivated_staff_profile_is_refused(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    profile = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id == op.id)
        )
    ).scalar_one()
    profile.is_active = False
    await db_session.commit()
    try:
        resp = await client.get(f"{_STAFF}/tickets", headers=op.headers)
        assert resp.status_code == 403, resp.text
    finally:
        profile.is_active = True
        await db_session.commit()


@pytest.mark.asyncio
async def test_the_operator_side_needs_a_session(
    client: AsyncClient, comms: FakeComms
) -> None:
    assert (await client.get(f"{_STAFF}/tickets")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["operator", "sender", "is_supervisor", "participant"]
)
async def test_an_actor_name_is_refused_in_a_query_and_in_a_body(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms, field: str
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    resp = await client.get(f"{_STAFF}/tickets?{field}=x", headers=op.headers)
    assert resp.status_code == 400, resp.text
    resp = await _post(client, op, f"/tickets/{tid}/claim", {field: str(uuid4())})
    assert resp.status_code == 422, resp.text
    assert comms.calls_to("POST", "/claim") == []


@pytest.mark.asyncio
async def test_operator_reaching_comms_is_the_session(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    assert (await _post(client, op, f"/tickets/{tid}/claim")).status_code == 200
    resp = await client.post(
        f"{_STAFF}/threads/{tid}/messages",
        json={"body": "on it"},
        headers=_key(op.headers),
    )
    assert resp.status_code == 200, resp.text
    assert comms.calls_to("POST", "/claim")[0]["json"] == {"operator": str(op.id)}
    sent = comms.calls_to("POST", f"{tid}/messages")[-1]
    assert sent["json"]["sender"] == str(op.id)


# ---------------------------------------------------------------------------
# The list: every ticket, its filters, its cursor
# ---------------------------------------------------------------------------


async def _ids(client: AsyncClient, op: Op, **params: Any) -> list[str]:
    out: list[str] = []
    cursor = None
    while True:
        query = {k: v for k, v in params.items() if v is not None}
        if cursor:
            query["cursor"] = cursor
        resp = await client.get(f"{_STAFF}/tickets", params=query, headers=op.headers)
        assert resp.status_code == 200, resp.text
        page = resp.json()
        out += [row["id"] for row in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            return out


@pytest.mark.asyncio
async def test_every_operator_sees_every_ticket(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    taker = await _operator(client, db_session, comms)
    other = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    assert (await _post(client, taker, f"/tickets/{tid}/claim")).status_code == 200
    assert tid in await _ids(client, other, limit=100)
    card = await client.get(f"{_STAFF}/tickets/{tid}", headers=other.headers)
    assert card.json()["claimed_by"]["user_id"] == str(taker.id)


@pytest.mark.asyncio
async def test_the_list_is_newest_first_and_the_cursor_takes_each_once(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client)
    made = [(await _ticket(client, person=person))[0] for _ in range(5)]
    for limit in (1, 2, 100):
        listed = [i for i in await _ids(client, op, limit=limit) if i in made]
        assert listed == list(reversed(made)), limit


@pytest.mark.asyncio
async def test_spam_is_its_own_tab(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    spam, _, _ = await _ticket(client)
    kept, _, _ = await _ticket(client)
    await _set(db_session, spam, status="spam")
    every = await _ids(client, op, limit=100)
    assert kept in every
    assert spam not in every
    tab = await _ids(client, op, status="spam", limit=100)
    assert spam in tab
    assert kept not in tab


@pytest.mark.asyncio
async def test_categories_repeat_as_or(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    kyc, _, _ = await _ticket(client, topic="kyc")
    pay, _, _ = await _ticket(client, topic="payments")
    tech, _, _ = await _ticket(client, topic="technical")
    resp = await client.get(
        f"{_STAFF}/tickets",
        params=[
            ("category", "verification"),
            ("category", "tech"),
            ("category", "tech"),
            ("limit", 100),
        ],
        headers=op.headers,
    )
    ids = {row["id"] for row in resp.json()["items"]}
    assert {kyc, tech} <= ids
    assert pay not in ids
    resp = await client.get(f"{_STAFF}/tickets?category=lottery", headers=op.headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_a_day_is_the_operators_with_its_zone(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    created = (await _row(db_session, tid)).created_at
    # The edges are instants with their zone: written in UTC+3 they are
    # the same instants as in UTC.
    plus3 = timezone(timedelta(hours=3))
    edge_from = (created - timedelta(minutes=1)).astimezone(plus3)
    edge_to = (created + timedelta(minutes=1)).astimezone(plus3)
    inside = await _ids(
        client,
        op,
        created_from=edge_from.isoformat(),
        created_to=edge_to.isoformat(),
        limit=100,
    )
    assert tid in inside
    after = await _ids(client, op, created_from=edge_to.isoformat(), limit=100)
    assert tid not in after
    naive = datetime(2026, 10, 25, 0, 0).isoformat()
    resp = await client.get(
        f"{_STAFF}/tickets", params={"created_from": naive}, headers=op.headers
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "support_date_without_zone"


@pytest.mark.asyncio
async def test_a_card_is_a_tickets_and_nothing_elses(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, user_id = await _ticket(client, topic="kyc")
    card = await client.get(f"{_STAFF}/tickets/{tid}", headers=op.headers)
    assert card.status_code == 200
    assert card.json()["opener"]["user_id"] == str(user_id)
    assert (card.json()["topic"], card.json()["category"]) == ("kyc", "verification")
    assert card.json()["history_thread_id"] is None
    history = comms.add_thread(client=user_id)
    db_session.add(SupportThread(user_id=user_id, comms_thread_id=UUID(history)))
    await db_session.commit()
    for other in (history, str(uuid4())):
        resp = await client.get(f"{_STAFF}/tickets/{other}", headers=op.headers)
        assert resp.status_code == 404
    # The pair: the card now names the person's history.
    card = await client.get(f"{_STAFF}/tickets/{tid}", headers=op.headers)
    assert card.json()["history_thread_id"] == history


# ---------------------------------------------------------------------------
# 3. Taking and handing over
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_taking_is_the_holders_and_a_conflict_for_anyone_else(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    me = await _operator(client, db_session, comms)
    colleague = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    first = await _post(client, me, f"/tickets/{tid}/claim")
    again = await _post(client, me, f"/tickets/{tid}/claim")
    assert first.status_code == again.status_code == 200
    assert again.json()["claimed_by"]["user_id"] == str(me.id)
    resp = await _post(client, colleague, f"/tickets/{tid}/claim")
    assert resp.status_code == 409
    assert resp.json()["error"] == "support_thread_already_claimed"
    assert (await _row(db_session, tid)).claimed_by_user_id == me.id


@pytest.mark.asyncio
async def test_handing_over_tells_the_new_taker_and_returning_tells_everyone(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    me = await _operator(client, db_session, comms)
    colleague = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client, topic="kyc")
    await _post(client, me, f"/tickets/{tid}/claim")

    to_colleague = {"assignee": str(colleague.id)}
    resp = await _post(client, me, f"/tickets/{tid}/assign", to_colleague)
    assert resp.status_code == 200, resp.text
    assert resp.json()["claimed_by"]["user_id"] == str(colleague.id)
    assert comms.threads[tid]["assignee"] == str(colleague.id)
    # The same operator again: nothing changes, nobody is told twice.
    again = await _post(client, me, f"/tickets/{tid}/assign", to_colleague)
    assert again.status_code == 200

    resp = await _post(client, colleague, f"/tickets/{tid}/release")
    assert resp.status_code == 200
    assert resp.json()["claimed_by"] is None

    handovers = [
        s
        for s in await _signals(db_session, tid)
        if s["type"] != "support.message_received"
    ]
    assert [(s["type"], s["target_type"], s["target_value"]) for s in handovers] == [
        ("support.ticket_assigned", "user", str(colleague.id)),
        ("support.ticket_released", "group", "support_operators"),
    ]
    assigned = handovers[0]["action_data"]
    assert assigned["action"] == "open_support_ticket"
    assert assigned["params"] == {"id": tid}
    assert assigned["topic_en"] == "Verification (KYC)"
    assert assigned["actor_name"]


@pytest.mark.asyncio
async def test_handing_over_to_a_non_operator_never_reaches_comms(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    me = await _operator(client, db_session, comms)
    tid, _, person_id = await _ticket(client)
    for target in (person_id, uuid4()):
        resp = await _post(
            client, me, f"/tickets/{tid}/assign", {"assignee": str(target)}
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"] == "support_assignee_not_operator"
    assert comms.calls_to("POST", "/assign") == []


# ---------------------------------------------------------------------------
# 4. Replying
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replying_without_taking_says_what_to_do(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    resp = await client.post(
        f"{_STAFF}/threads/{tid}/messages",
        json={"body": "hi"},
        headers=_key(op.headers),
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "support_thread_not_claimed"


@pytest.mark.asyncio
async def test_the_history_reads_but_never_takes_a_reply(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    _, user_id = await _person(client)
    history = comms.add_thread(client=user_id, assignee=op.id)
    comms.post(history, user_id, "from before")
    db_session.add(SupportThread(user_id=user_id, comms_thread_id=UUID(history)))
    await db_session.commit()
    feed = await client.get(f"{_STAFF}/threads/{history}/messages", headers=op.headers)
    assert [m["body"] for m in feed.json()["items"]] == ["from before"]
    resp = await client.post(
        f"{_STAFF}/threads/{history}/messages",
        json={"body": "x"},
        headers=_key(op.headers),
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "support_history_read_only"
    assert comms.calls_to("POST", f"{history}/messages") == []


@pytest.mark.asyncio
async def test_an_unknown_thread_never_reaches_comms(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    stranger = comms.add_thread(client=uuid4())  # in comms, not ours
    for method, path in (
        ("GET", f"/threads/{stranger}/messages"),
        ("POST", f"/tickets/{stranger}/claim"),
        ("POST", f"/tickets/{stranger}/reopen"),
    ):
        resp = await client.request(method, f"{_STAFF}{path}", headers=op.headers)
        assert resp.status_code == 404, (path, resp.text)
    assert [c for c in comms.calls if stranger in c["path"]] == []


@pytest.mark.asyncio
async def test_an_empty_reply_is_refused(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    await _post(client, op, f"/tickets/{tid}/claim")
    resp = await client.post(
        f"{_STAFF}/threads/{tid}/messages",
        json={"body": ""},
        headers=_key(op.headers),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Closing and returning to work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["resolved", "rejected", "duplicate", "spam"])
async def test_an_open_ticket_closes_four_ways_and_comms_hears_resolved(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms, status: str
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    seen = (await _row(db_session, tid)).version  # a number, not the row
    resp = await _post(client, op, f"/tickets/{tid}/status", {"status": status})
    assert resp.status_code == 200, resp.text
    after = await _row(db_session, tid)
    assert (after.status, after.version) == (status, seen + 1)
    assert comms.threads[tid]["status"] == "resolved"  # never `closed`
    again = await _post(client, op, f"/tickets/{tid}/status", {"status": "resolved"})
    assert again.status_code == 409
    assert again.json()["error"] == "support_ticket_not_open"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["open", "closed", "lost"])
async def test_a_status_outside_the_four_is_refused_before_comms(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms, status: str
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    resp = await _post(client, op, f"/tickets/{tid}/status", {"status": status})
    assert resp.status_code == 422
    assert comms.calls_to("POST", "/status") == []


@pytest.mark.asyncio
async def test_a_change_made_meanwhile_wins_and_this_one_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    comms: FakeComms,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The person writes while the operator closes: the version the close
    read is gone when it writes, so the close is refused and the ticket
    stays as the message left it."""
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    row = await _row(db_session, tid)

    async def _meanwhile(*args: Any, **kwargs: Any) -> Any:
        if args[1].endswith("/status"):
            await db_session.execute(
                update(SupportTicket)
                .where(SupportTicket.support_thread_id == row.support_thread_id)
                .values(version=SupportTicket.version + 1)
            )
            await db_session.commit()
        return await comms(*args, **kwargs)

    monkeypatch.setattr("app.modules.support.service.comms_request", _meanwhile)
    resp = await _post(client, op, f"/tickets/{tid}/status", {"status": "resolved"})
    assert resp.status_code == 409
    assert resp.json()["error"] == "support_ticket_changed"
    assert (await _row(db_session, tid)).status == "open"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["resolved", "rejected", "duplicate", "spam"])
async def test_back_to_work_from_every_closing(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms, status: str
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    await _post(client, op, f"/tickets/{tid}/status", {"status": status})
    resp = await _post(client, op, f"/tickets/{tid}/reopen")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "open"
    assert comms.threads[tid]["status"] == "open"
    again = await _post(client, op, f"/tickets/{tid}/reopen")
    assert again.status_code == 409
    assert again.json()["error"] == "support_ticket_open"


@pytest.mark.asyncio
async def test_spam_past_its_retention_does_not_come_back(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    from app.core.config import settings

    op = await _operator(client, db_session, comms)
    old, _, _ = await _ticket(client)
    young, _, _ = await _ticket(client)
    retention = timedelta(days=settings.support_spam_retention_days)
    now = datetime.now(UTC)
    await _set(
        db_session,
        old,
        status="spam",
        status_changed_at=now - retention - timedelta(minutes=1),
    )
    await _set(
        db_session,
        young,
        status="spam",
        status_changed_at=now - retention + timedelta(minutes=5),
    )
    resp = await _post(client, op, f"/tickets/{old}/reopen")
    assert resp.status_code == 409
    assert resp.json()["error"] == "support_spam_expired"
    assert comms.calls_to("POST", f"{old}/status") == []
    assert (await _post(client, op, f"/tickets/{young}/reopen")).status_code == 200


# ---------------------------------------------------------------------------
# The signal on a person's message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_persons_message_signals_every_operator_until_one_takes_it(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    tid, person, _ = await _ticket(client, topic="withdrawal")
    await _post(client, op, f"/tickets/{tid}/claim")
    resp = await client.post(
        f"{_PERSON}/messages", json={"body": "and?"}, headers=_key(person)
    )
    assert resp.status_code == 200

    received = [
        s
        for s in await _signals(db_session, tid)
        if s["type"] == "support.message_received"
    ]
    assert [(s["target_type"], s["target_value"]) for s in received] == [
        ("group", "support_operators"),
        ("user", str(op.id)),
    ]
    first = received[0]
    assert first["title"] == "New message to support"  # SUPPORT_LANGUAGE=en here
    assert "Withdrawals" in first["body"]
    data = first["action_data"]
    assert (data["action"], data["params"]) == ("open_support_ticket", {"id": tid})
    assert (data["topic_en"], data["topic_ru"]) == ("Withdrawals", "Вывод средств")
    assert data["sender_name"]
    # One message, one signal: keyed by the comms message.
    keys = [s["idempotency_key"] for s in received]
    assert len(set(keys)) == 2
    assert all(k.startswith("aivis:support-message:") for k in keys)


@pytest.mark.asyncio
async def test_a_message_into_spam_signals_nobody(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    tid, person, _ = await _ticket(client)
    await _set(db_session, tid, status="spam")
    before = len(await _signals(db_session, tid))
    resp = await client.post(
        f"{_PERSON}/messages", json={"body": "buy"}, headers=_key(person)
    )
    assert resp.status_code == 200
    assert len(await _signals(db_session, tid)) == before
    assert before == 1, "the pair: the appeal itself was signalled"


# ---------------------------------------------------------------------------
# 5. comms down, and the operator list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_being_down_is_an_answer_not_a_crash(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    tid, _, _ = await _ticket(client)
    comms.down = True
    for path, body in (
        (f"/tickets/{tid}/claim", None),
        (f"/tickets/{tid}/status", {"status": "resolved"}),
        (f"/tickets/{tid}/release", None),
    ):
        resp = await _post(client, op, path, body)
        assert resp.status_code == 502, (path, resp.text)
    assert (await _row(db_session, tid)).status == "open"
    # The list is our table: comms down changes nothing there.
    assert tid in await _ids(client, op, limit=100)


@pytest.mark.asyncio
async def test_the_operator_list_is_the_active_staff(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    _, person_id = await _person(client)
    resp = await client.get(f"{_STAFF}/operators", headers=op.headers)
    ids = [p["user_id"] for p in resp.json()["items"]]
    assert str(op.id) in ids
    assert str(person_id) not in ids
