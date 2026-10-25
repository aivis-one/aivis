# =============================================================================
# AIVIS.ONE Backend -- Support, the person's side (T-65, H40 tickets)
# =============================================================================
#
# Rewritten for H40: the person no longer opens "their thread" -- they have
# ONE conversation of many tickets, and no route names a thread. What the
# T-65 suite pinned and still holds is kept here, on the new routes:
#
#   1. no actor name is readable from a request (body, query), and the
#      session is what reaches comms;
#   2. a session is required;
#   3. comms being down, or not knowing the person yet, is an answer --
#      never a 500 and never a silent success;
#   4. one press of "send" is one message: the same Idempotency-Key is the
#      same message (and the same ticket), another text under it a 409.
#
# What H40 adds:
#
#   5. the form: every submit is a new ticket of the chosen topic, its
#      category from the one table (models.TOPICS);
#   6. a message in the conversation goes to the latest open ticket, else
#      the latest ticket (back to work), else a new ticket "other" -- the
#      pre-H40 history is never written into;
#   7. the feed is every thread of the person glued into one, newest first,
#      every message exactly once across the pages -- and nobody else's;
#   8. unread is summed over the person's threads; with none, 0 without
#      asking comms.
#
# comms is the stateful fake of tests/support_fake.py.
# =============================================================================

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.comms import CommsRejectedError, CommsTimeoutError
from app.core.events.models import OutboxEvent
from app.modules.support.models import TOPICS, SupportThread, SupportTicket
from app.modules.support.schemas import TicketIn
from tests.helpers import auth_headers, register_user
from tests.support_fake import FakeComms, install

_BASE = "/api/v1/support"


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> FakeComms:
    return install(monkeypatch)


async def _person(client: AsyncClient) -> tuple[dict[str, str], UUID]:
    body = await register_user(client)
    return auth_headers(body["session_token"]), UUID(body["user"]["id"])


def _key(headers: dict[str, str], key: str | None = None) -> dict[str, str]:
    """The headers of one press of "send": the client's Idempotency-Key."""
    return {**headers, "Idempotency-Key": key or str(uuid4())}


async def _appeal(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    topic: str = "payments",
    body: str = "help",
    key: str | None = None,
) -> Any:
    return await client.post(
        f"{_BASE}/tickets",
        json={"topic": topic, "body": body},
        headers=_key(headers, key),
    )


async def _write(
    client: AsyncClient,
    headers: dict[str, str],
    body: str = "hello",
    key: str | None = None,
) -> Any:
    return await client.post(
        f"{_BASE}/messages",
        json={"body": body},
        headers=_key(headers, key),
    )


async def _tickets(session: AsyncSession, user_id: UUID) -> list[SupportTicket]:
    session.expire_all()
    return list(
        (
            await session.execute(
                select(SupportTicket)
                .join(
                    SupportThread, SupportThread.id == SupportTicket.support_thread_id
                )
                .where(SupportThread.user_id == user_id)
                .order_by(SupportTicket.created_at)
            )
        ).scalars()
    )


async def _history(session: AsyncSession, comms: FakeComms, user_id: UUID) -> str:
    """The person's pre-H40 conversation: a dm thread with a pointer and
    no ticket."""
    thread_id = comms.add_thread(client=user_id, kind="dm")
    session.add(SupportThread(user_id=user_id, comms_thread_id=UUID(thread_id)))
    await session.commit()
    return thread_id


@pytest.fixture(autouse=True)
async def _no_signal_residue(db_session: AsyncSession) -> Any:
    """The operator signals these tests cause are outbox rows; the relay
    suite counts the outbox, so they do not outlive the test."""
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
# 1-2. Who is asking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["sender", "participant", "client", "operator", "user_id"]
)
async def test_an_actor_name_in_a_body_is_refused(
    client: AsyncClient, comms: FakeComms, field: str
) -> None:
    headers, _ = await _person(client)
    for path, body in (
        ("/tickets", {"topic": "payments", "body": "x"}),
        ("/messages", {"body": "x"}),
    ):
        resp = await client.post(
            f"{_BASE}{path}",
            json={**body, field: str(uuid4())},
            headers=_key(headers),
        )
        assert resp.status_code == 422, (path, resp.text)
    assert comms.calls_to("POST", "/messages") == []
    assert comms.calls_to("POST", "/api/v1/threads") == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/tickets"),
        ("POST", "/messages"),
        ("GET", "/messages"),
        ("POST", "/read"),
        ("GET", "/unread"),
    ],
)
async def test_an_actor_name_in_a_query_is_refused(
    client: AsyncClient, comms: FakeComms, method: str, path: str
) -> None:
    headers, _ = await _person(client)
    bodies = {
        ("POST", "/tickets"): {"topic": "payments", "body": "x"},
        ("POST", "/messages"): {"body": "x"},
    }
    resp = await client.request(
        method,
        f"{_BASE}{path}?participant={uuid4()}",
        json=bodies.get((method, path)),
        headers=_key(headers),
    )
    assert resp.status_code == 400, resp.text
    assert "participant" in resp.text


@pytest.mark.asyncio
async def test_the_session_is_what_reaches_comms(
    client: AsyncClient, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    assert (await _appeal(client, headers)).status_code == 200
    assert (await _write(client, headers)).status_code == 200
    created = comms.calls_to("POST", "/api/v1/threads")
    assert [c["json"]["client"] for c in created] == [str(user_id)]
    assert created[0]["json"]["kind"] == "ticket"
    senders = {c["json"]["sender"] for c in comms.calls_to("POST", "/messages")}
    assert senders == {str(user_id)}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, path",
    [
        ("POST", "/tickets"),
        ("POST", "/messages"),
        ("GET", "/messages"),
        ("POST", "/read"),
        ("GET", "/unread"),
    ],
)
async def test_support_requires_a_session(
    client: AsyncClient, comms: FakeComms, method: str, path: str
) -> None:
    resp = await client.request(method, f"{_BASE}{path}")
    assert resp.status_code == 401
    assert comms.calls == []


# ---------------------------------------------------------------------------
# 5. The form
# ---------------------------------------------------------------------------


def test_the_wire_offers_exactly_the_topics_of_the_table() -> None:
    """The form's Literal and the one table are the same set -- a topic in
    one and not the other would be a 422 for a real choice, or a choice
    with no category."""
    offered = set(TicketIn.model_fields["topic"].annotation.__args__)
    assert offered == set(TOPICS)
    assert offered, "the pair: the set is not empty"


@pytest.mark.asyncio
async def test_every_submit_is_a_new_ticket_with_its_topic_and_category(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    first = await _appeal(client, headers, topic="kyc", body="my documents")
    second = await _appeal(client, headers, topic="withdrawal", body="my money")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["ticket"]["id"] != second.json()["ticket"]["id"]

    tickets = await _tickets(db_session, user_id)
    assert [(t.topic, t.category, t.status) for t in tickets] == [
        ("kyc", "verification", "open"),
        ("withdrawal", "withdrawals", "open"),
    ]
    # Each ticket's first message is the text, in its own thread.
    for answer, text in ((first, "my documents"), (second, "my money")):
        tid = answer.json()["ticket"]["id"]
        assert [m["body"] for m in comms.messages[tid]] == [text]


@pytest.mark.asyncio
async def test_the_same_key_is_the_same_ticket_and_the_same_message(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    key = str(uuid4())
    one = await _appeal(client, headers, key=key)
    two = await _appeal(client, headers, key=key)
    assert one.status_code == two.status_code == 200
    assert one.json() == two.json()
    assert len(await _tickets(db_session, user_id)) == 1
    assert len(comms.threads) == 1
    assert sum(len(v) for v in comms.messages.values()) == 1


@pytest.mark.asyncio
async def test_another_text_under_the_same_key_is_a_conflict(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    key = str(uuid4())
    assert (await _appeal(client, headers, key=key, body="one")).status_code == 200
    resp = await _appeal(client, headers, key=key, body="two")
    assert resp.status_code == 409, resp.text
    assert len(await _tickets(db_session, user_id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"topic": "lottery", "body": "x"},
        {"topic": "payments", "body": ""},
        {"topic": "payments"},
        {"body": "x"},
    ],
)
async def test_a_bad_appeal_is_refused_before_comms(
    client: AsyncClient, comms: FakeComms, body: dict
) -> None:
    headers, _ = await _person(client)
    resp = await client.post(f"{_BASE}/tickets", json=body, headers=_key(headers))
    assert resp.status_code == 422, resp.text
    assert comms.calls_to("POST", "/api/v1/threads") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [None, "", "x" * 300, "bad key"])
async def test_a_message_without_a_usable_key_never_reaches_comms(
    client: AsyncClient, comms: FakeComms, key: str | None
) -> None:
    headers, _ = await _person(client)
    sent = dict(headers)
    if key is not None:
        sent["Idempotency-Key"] = key
    for path, body in (
        ("/tickets", {"topic": "payments", "body": "x"}),
        ("/messages", {"body": "x"}),
    ):
        resp = await client.post(f"{_BASE}{path}", json=body, headers=sent)
        assert resp.status_code == 422, (path, resp.text)
    assert comms.calls_to("POST", "/api/v1/threads") == []
    assert comms.calls_to("POST", "/messages") == []


# ---------------------------------------------------------------------------
# 6. Where a message in the conversation goes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_first_message_opens_a_ticket_other(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    resp = await _write(client, headers, "is anybody there?")
    assert resp.status_code == 200, resp.text
    tickets = await _tickets(db_session, user_id)
    assert [(t.topic, t.category) for t in tickets] == [("other", "other")]


@pytest.mark.asyncio
async def test_a_retried_first_message_is_one_ticket_and_one_message(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    """The retry finds the ticket the first attempt opened and posts into
    it under the same key -- comms answers with the message it has."""
    headers, user_id = await _person(client)
    key = str(uuid4())
    one = await _write(client, headers, "hi", key=key)
    two = await _write(client, headers, "hi", key=key)
    assert one.status_code == two.status_code == 200
    assert one.json()["id"] == two.json()["id"]
    assert len(await _tickets(db_session, user_id)) == 1
    assert sum(len(v) for v in comms.messages.values()) == 1


@pytest.mark.asyncio
async def test_a_message_goes_to_the_latest_open_ticket(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    older = (await _appeal(client, headers, topic="kyc")).json()["ticket"]["id"]
    newer = (await _appeal(client, headers, topic="technical")).json()["ticket"]["id"]
    # The newer one is closed: the open one is the latest OPEN.
    tickets = await _tickets(db_session, user_id)
    tickets[1].status = "resolved"
    await db_session.commit()

    assert (await _write(client, headers, "about kyc")).status_code == 200
    assert comms.messages[older][0]["body"] == "about kyc"
    assert comms.messages[newer][0]["body"] != "about kyc"


@pytest.mark.asyncio
async def test_with_none_open_the_latest_ticket_returns_to_work(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    await _appeal(client, headers, topic="kyc")
    latest = (await _appeal(client, headers, topic="payments")).json()["ticket"]["id"]
    for ticket in await _tickets(db_session, user_id):
        ticket.status = "resolved"
    await db_session.commit()
    before = (await _tickets(db_session, user_id))[1].version

    assert (await _write(client, headers, "again")).status_code == 200
    tickets = await _tickets(db_session, user_id)
    assert [t.status for t in tickets] == ["resolved", "open"]
    assert tickets[1].version == before + 1
    assert comms.messages[latest][0]["body"] == "again"
    assert comms.threads[latest]["status"] == "open"


@pytest.mark.asyncio
async def test_a_message_into_spam_stays_spam(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    tid = (await _appeal(client, headers)).json()["ticket"]["id"]
    ticket = (await _tickets(db_session, user_id))[0]
    ticket.status = "spam"
    await db_session.commit()

    assert (await _write(client, headers, "buy now")).status_code == 200
    assert (await _tickets(db_session, user_id))[0].status == "spam"
    assert comms.messages[tid][0]["body"] == "buy now"  # the pair: it was posted


@pytest.mark.asyncio
async def test_the_history_is_never_written_into(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    history = await _history(db_session, comms, user_id)
    assert (await _write(client, headers, "new question")).status_code == 200
    assert comms.messages.get(history, []) == []
    tickets = await _tickets(db_session, user_id)
    assert [t.topic for t in tickets] == ["other"]


# ---------------------------------------------------------------------------
# 7. One feed
# ---------------------------------------------------------------------------


async def _feed_pages(
    client: AsyncClient, headers: dict[str, str], limit: int
) -> list[list[str]]:
    pages: list[list[str]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        resp = await client.get(f"{_BASE}/messages", params=params, headers=headers)
        assert resp.status_code == 200, resp.text
        page = resp.json()
        pages.append([m["body"] for m in page["items"]])
        cursor = page["next_cursor"]
        if cursor is None:
            return pages
        assert len(pages) < 50, "the cursor never ends"


@pytest.mark.asyncio
async def test_the_feed_glues_every_thread_newest_first(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    history = await _history(db_session, comms, user_id)
    comms.post(history, user_id, "h1")
    a = (await _appeal(client, headers, body="a1")).json()["ticket"]["id"]
    comms.post(history, user_id, "h2")
    b = (await _appeal(client, headers, body="b1")).json()["ticket"]["id"]
    comms.post(a, user_id, "a2")
    comms.post(b, user_id, "b2")

    expected = ["b2", "a2", "b1", "h2", "a1", "h1"]
    for limit in (1, 2, 4, 100):
        pages = await _feed_pages(client, headers, limit)
        flat = [body for page in pages for body in page]
        assert flat == expected, (limit, pages)
        assert all(len(page) <= limit for page in pages)


@pytest.mark.asyncio
async def test_the_feed_shows_nobody_elses_messages(
    client: AsyncClient, comms: FakeComms
) -> None:
    mine, _ = await _person(client)
    theirs, _ = await _person(client)
    await _appeal(client, theirs, body="their secret")
    await _appeal(client, mine, body="my question")
    pages = await _feed_pages(client, mine, 20)
    assert pages == [["my question"]]


@pytest.mark.asyncio
async def test_an_empty_conversation_is_an_empty_page(
    client: AsyncClient, comms: FakeComms
) -> None:
    headers, _ = await _person(client)
    resp = await client.get(f"{_BASE}/messages", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", ["garbage", "e30", "eyJhIjoxfQ"])
async def test_a_malformed_cursor_is_a_400(
    client: AsyncClient, comms: FakeComms, cursor: str
) -> None:
    headers, _ = await _person(client)
    await _appeal(client, headers)
    resp = await client.get(
        f"{_BASE}/messages", params={"cursor": cursor}, headers=headers
    )
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# 8. Read and unread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unread_is_summed_and_read_clears_every_thread(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    staff = uuid4()
    history = await _history(db_session, comms, user_id)
    a = (await _appeal(client, headers)).json()["ticket"]["id"]
    comms.post(history, staff, "old reply")
    comms.post(a, staff, "reply 1")
    comms.post(a, staff, "reply 2")

    resp = await client.get(f"{_BASE}/unread", headers=headers)
    assert resp.json() == {"unread": 3}
    resp = await client.post(f"{_BASE}/read", headers=headers)
    assert resp.json() == {"unread": 0}
    assert len(comms.calls_to("POST", "/read")) == 2  # one per thread
    assert (await client.get(f"{_BASE}/unread", headers=headers)).json() == {
        "unread": 0
    }


@pytest.mark.asyncio
async def test_no_conversation_is_zero_without_asking_comms(
    client: AsyncClient, comms: FakeComms
) -> None:
    headers, _ = await _person(client)
    resp = await client.get(f"{_BASE}/unread", headers=headers)
    assert resp.json() == {"unread": 0}
    assert comms.calls_to("POST", "/unread-counts") == []


# ---------------------------------------------------------------------------
# 3. comms failing is an answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_down_is_a_502_and_no_ticket(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    comms.down = True
    for resp in (
        await _appeal(client, headers),
        await _write(client, headers),
    ):
        assert resp.status_code == 502, resp.text
    assert await _tickets(db_session, user_id) == []


@pytest.mark.asyncio
async def test_a_timeout_is_an_answer(client: AsyncClient, comms: FakeComms) -> None:
    headers, _ = await _person(client)
    await _appeal(client, headers)
    comms.fail[("POST", "/messages")] = CommsTimeoutError()
    resp = await _write(client, headers)
    assert resp.status_code == 504, resp.text


@pytest.mark.asyncio
async def test_a_person_comms_does_not_know_yet_is_not_ready(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    headers, user_id = await _person(client)
    comms.recipients.discard(str(user_id))
    resp = await _appeal(client, headers)
    assert resp.status_code == 502
    assert resp.json()["error"] == "comms_recipient_pending"
    assert await _tickets(db_session, user_id) == []


@pytest.mark.asyncio
async def test_a_malformed_thread_answer_is_a_refusal_not_a_crash(
    client: AsyncClient,
    db_session: AsyncSession,
    comms: FakeComms,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, user_id = await _person(client)

    async def _no_id(*args: Any, **kwargs: Any) -> Any:
        if args[:2] == ("POST", "/api/v1/threads"):
            return {"status": "open"}
        return await comms(*args, **kwargs)

    monkeypatch.setattr("app.modules.support.service.comms_request", _no_id)
    resp = await _appeal(client, headers)
    assert resp.status_code == 502, resp.text
    assert await _tickets(db_session, user_id) == []


@pytest.mark.asyncio
async def test_a_refusal_comms_models_is_forwarded_in_its_class(
    client: AsyncClient, comms: FakeComms
) -> None:
    headers, _ = await _person(client)
    await _appeal(client, headers)
    comms.fail[("POST", "/messages")] = CommsRejectedError(
        status_code=422, error_class="validation"
    )
    resp = await _write(client, headers)
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_two_people_never_share_a_ticket(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    """The same client key from two people is two tickets: the key the
    product sends comms carries the person."""
    one, one_id = await _person(client)
    two, two_id = await _person(client)
    key = str(uuid4())
    assert (await _appeal(client, one, key=key)).status_code == 200
    assert (await _appeal(client, two, key=key)).status_code == 200
    assert len(await _tickets(db_session, one_id)) == 1
    assert len(await _tickets(db_session, two_id)) == 1
    keys = {c["key"] for c in comms.calls_to("POST", "/api/v1/threads")}
    assert len(keys) == 2
    count = await db_session.execute(select(func.count()).select_from(SupportTicket))
    assert count.scalar_one() >= 2
