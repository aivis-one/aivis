# =============================================================================
# AIVIS.ONE Backend -- support: the rating of a ticket and the statistics (H41)
# =============================================================================
#
# After velo's test_support_rating_be162.py, on this product's routes and
# the fake comms of tests/support_fake.py. Pinned:
#
#   1. RESOLVED records who resolved and asks the person at once -- one
#      request per move to RESOLVED while unrated, in their language,
#      in-app, opening this ticket's rating; no other close asks;
#   2. one rating per ticket, by its person, of a RESOLVED ticket only;
#      the comment as written, the interface language beside it, the
#      operator it rated kept when the ticket moves on;
#   3. the person's pending and given ratings;
#   4. the rating and the resolver in the list row and the card alike;
#      the list filtered by rating;
#   5. the statistics: categories without spam add up to the list without
#      spam for the same period; spam is live plus tombstones; ratings by
#      category and by the operator they rated; the period's edges.
#
# Statistics count every ticket of the period in the shared test database,
# so the tests of section 5 move their own tickets into a period of their
# own, far in the past, and ask for that period alone.
# =============================================================================

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import OutboxEvent
from app.modules.support.models import (
    CATEGORIES,
    SupportSpamTombstone,
    SupportThread,
    SupportTicket,
)
from app.modules.users.models import User
from tests.helpers import auth_headers, create_staff_user, register_user
from tests.support_fake import FakeComms, install

_PERSON = "/api/v1/support"
_STAFF = "/api/v1/staff/support"
_REQUEST = "support.rating_requested"


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> FakeComms:
    return install(monkeypatch)


@pytest.fixture(autouse=True)
async def _no_residue(db_session: AsyncSession) -> Any:
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


class Op:
    def __init__(self, user: Any, token: str) -> None:
        self.id = user.id
        self.headers = auth_headers(token)


class Person:
    def __init__(self, body: dict) -> None:
        self.id = UUID(body["user"]["id"])
        self.headers = auth_headers(body["session_token"])


async def _operator(client: AsyncClient, session: AsyncSession, comms: FakeComms) -> Op:
    user, token = await create_staff_user(client, session)
    comms.serve(user.id)
    return Op(user, token)


async def _person(
    client: AsyncClient, session: AsyncSession, *, language: str = "en"
) -> Person:
    person = Person(await register_user(client))
    await session.execute(
        update(User).where(User.id == person.id).values(language=language)
    )
    await session.commit()
    return person


async def _ticket(client: AsyncClient, person: Person, *, topic: str = "kyc") -> str:
    resp = await client.post(
        f"{_PERSON}/tickets",
        json={"topic": topic, "body": "help"},
        headers={**person.headers, "Idempotency-Key": str(uuid4())},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["ticket"]["id"]


async def _close(
    client: AsyncClient, op: Op, tid: str, status: str = "resolved"
) -> Any:
    resp = await client.post(
        f"{_STAFF}/tickets/{tid}/status", json={"status": status}, headers=op.headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _reopen(client: AsyncClient, op: Op, tid: str) -> None:
    resp = await client.post(f"{_STAFF}/tickets/{tid}/reopen", headers=op.headers)
    assert resp.status_code == 200, resp.text


async def _rate(client: AsyncClient, person: Person, tid: str, body: Any) -> Any:
    return await client.post(
        f"{_PERSON}/tickets/{tid}/rating", json=body, headers=person.headers
    )


async def _row(session: AsyncSession, tid: str) -> SupportTicket:
    session.expire_all()
    return (
        await session.execute(
            select(SupportTicket)
            .join(SupportThread, SupportThread.id == SupportTicket.support_thread_id)
            .where(SupportThread.comms_thread_id == UUID(tid))
        )
    ).scalar_one()


async def _requests(session: AsyncSession, tid: str) -> list[dict]:
    session.expire_all()
    rows = (
        await session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.payload["type"].astext == _REQUEST,
                OutboxEvent.payload["action_data"]["params"]["id"].astext == tid,
            )
            .order_by(OutboxEvent.id)
        )
    ).scalars()
    return [r.payload for r in rows]


# ---------------------------------------------------------------------------
# 1. The request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolved_asks_the_person_at_once_and_records_the_resolver(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    card = await _close(client, op, tid)
    assert card["resolved_by"]["user_id"] == str(op.id)
    assert (await _row(db_session, tid)).resolved_by_user_id == op.id

    [request] = await _requests(db_session, tid)
    assert (request["target_type"], request["target_value"]) == ("user", str(person.id))
    assert request["title"] == "How did we do?"
    assert request["action_data"] == {
        "action": "open_support_rating",
        "params": {"id": tid},
    }
    version = (await _row(db_session, tid)).version
    assert request["idempotency_key"] == f"aivis:support-rating:{tid}:{version}"


@pytest.mark.asyncio
async def test_the_request_is_in_the_persons_language(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    for language, title in (
        ("ru", "Как мы помогли?"),
        ("RU", "Как мы помогли?"),
        ("de", "How did we do?"),
    ):
        person = await _person(client, db_session, language=language)
        tid = await _ticket(client, person)
        await _close(client, op, tid)
        [request] = await _requests(db_session, tid)
        assert request["title"] == title, language


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["rejected", "duplicate", "spam"])
async def test_no_other_close_asks_or_names_a_resolver(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms, status: str
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    card = await _close(client, op, tid, status)
    assert card["resolved_by"] is None
    assert await _requests(db_session, tid) == []


@pytest.mark.asyncio
async def test_resolved_again_asks_again_unless_rated(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    first = await _operator(client, db_session, comms)
    second = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)

    await _close(client, first, tid)
    await _reopen(client, first, tid)
    assert (await _row(db_session, tid)).resolved_by_user_id == first.id  # kept
    await _close(client, second, tid)
    requests = await _requests(db_session, tid)
    assert len(requests) == 2
    assert len({r["idempotency_key"] for r in requests}) == 2
    assert (await _row(db_session, tid)).resolved_by_user_id == second.id

    assert (await _rate(client, person, tid, {"stars": 5})).status_code == 200
    await _reopen(client, first, tid)
    await _close(client, first, tid)
    assert len(await _requests(db_session, tid)) == 2  # rated: never again
    row = await _row(db_session, tid)
    assert (row.resolved_by_user_id, row.rated_resolver_user_id) == (
        first.id,
        second.id,
    )


@pytest.mark.asyncio
async def test_a_box_without_comms_asks_nobody(
    client: AsyncClient,
    db_session: AsyncSession,
    comms: FakeComms,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    monkeypatch.setattr(settings, "comms_api_url", "")
    await _close(client, op, tid)
    assert await _requests(db_session, tid) == []
    assert (await _row(db_session, tid)).resolved_by_user_id == op.id  # the pair


# ---------------------------------------------------------------------------
# 2. The rating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_person_rates_a_resolved_ticket_once(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session, language="ru-RU")
    tid = await _ticket(client, person)
    await _close(client, op, tid)

    resp = await _rate(
        client, person, tid, {"stars": 4, "comment": "  быстро, спасибо  "}
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["stars"], resp.json()["comment"]) == (4, "быстро, спасибо")
    row = await _row(db_session, tid)
    assert (row.rating, row.rating_comment, row.rating_locale) == (
        4,
        "быстро, спасибо",
        "ru",
    )
    assert row.rated_at is not None
    assert row.rated_resolver_user_id == op.id

    again = await _rate(client, person, tid, {"stars": 1})
    assert again.status_code == 409
    assert again.json()["error"] == "support_ticket_not_ratable"
    assert (await _row(db_session, tid)).rating == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("comment", [None, "", "   "])
async def test_no_comment_is_null(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms, comment: Any
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    await _close(client, op, tid)
    body = {"stars": 3} if comment is None else {"stars": 3, "comment": comment}
    assert (await _rate(client, person, tid, body)).status_code == 200
    row = await _row(db_session, tid)
    assert (row.rating, row.rating_comment, row.rating_locale) == (3, None, "en")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "rejected", "duplicate", "reopened"])
async def test_only_a_resolved_ticket_is_rated(
    client: AsyncClient,
    db_session: AsyncSession,
    comms: FakeComms,
    status: str | None,
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    if status == "reopened":
        await _close(client, op, tid)
        await _reopen(client, op, tid)
    elif status is not None:
        await _close(client, op, tid, status)
    resp = await _rate(client, person, tid, {"stars": 5})
    assert resp.status_code == 409
    assert (await _row(db_session, tid)).rating is None


@pytest.mark.asyncio
async def test_a_persons_message_takes_the_rating_away(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    """Writing into a resolved ticket brings it back to work: it is no
    longer the person's to rate until it is resolved again."""
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    await _close(client, op, tid)
    resp = await client.post(
        f"{_PERSON}/messages",
        json={"body": "one more thing"},
        headers={**person.headers, "Idempotency-Key": str(uuid4())},
    )
    assert resp.status_code == 200
    assert (await _rate(client, person, tid, {"stars": 5})).status_code == 409


@pytest.mark.asyncio
async def test_nobody_elses_ticket_and_nothing_but_a_ticket(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    owner = await _person(client, db_session)
    stranger = await _person(client, db_session)
    tid = await _ticket(client, owner)
    await _close(client, op, tid)
    history = comms.add_thread(client=owner.id)
    db_session.add(SupportThread(user_id=owner.id, comms_thread_id=UUID(history)))
    await db_session.commit()
    for who, target in ((stranger, tid), (owner, history), (owner, str(uuid4()))):
        resp = await _rate(client, who, target, {"stars": 5})
        assert resp.status_code == 404, (target, resp.text)
    assert (await _row(db_session, tid)).rating is None
    # The pair: its own person can.
    assert (await _rate(client, owner, tid, {"stars": 5})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"stars": 0},
        {"stars": 6},
        {"stars": "4"},
        {"stars": 4.5},
        {"stars": True},
        {"stars": 4, "comment": "x" * 1001},
        {"stars": 4, "rater": str(uuid4())},
    ],
)
async def test_a_malformed_rating_is_a_422(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms, body: dict
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    await _close(client, op, tid)
    resp = await _rate(client, person, tid, body)
    assert resp.status_code == 422, resp.text
    assert (await _row(db_session, tid)).rating is None


@pytest.mark.asyncio
async def test_a_comment_of_the_longest_length_is_kept(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    await _close(client, op, tid)
    text_ = "x" * 1000
    assert (
        await _rate(client, person, tid, {"stars": 2, "comment": text_})
    ).status_code == 200
    assert (await _row(db_session, tid)).rating_comment == text_


@pytest.mark.asyncio
async def test_two_ratings_at_once_the_second_is_refused(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    await _close(client, op, tid)
    answers = await asyncio.gather(
        _rate(client, person, tid, {"stars": 5}),
        _rate(client, person, tid, {"stars": 1}),
    )
    assert sorted(a.status_code for a in answers) == [200, 409]
    winner = next(a for a in answers if a.status_code == 200).json()["stars"]
    assert (await _row(db_session, tid)).rating == winner


@pytest.mark.asyncio
async def test_a_deleted_resolver_leaves_the_rating(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    await _close(client, op, tid)
    await _rate(client, person, tid, {"stars": 5})
    await db_session.execute(delete(User).where(User.id == op.id))
    await db_session.commit()
    row = await _row(db_session, tid)
    assert (row.rating, row.resolved_by_user_id, row.rated_resolver_user_id) == (
        5,
        None,
        None,
    )


# ---------------------------------------------------------------------------
# 3. The person's ratings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_persons_pending_and_given_ratings(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    other = await _person(client, db_session)
    waiting = await _ticket(client, person, topic="payments")
    given = await _ticket(client, person, topic="kyc")
    still_open = await _ticket(client, person)
    theirs = await _ticket(client, other)
    for tid in (waiting, given, theirs):
        await _close(client, op, tid)
    await _rate(client, person, given, {"stars": 4, "comment": "ok"})

    resp = await client.get(f"{_PERSON}/ratings", headers=person.headers)
    assert resp.status_code == 200
    body = resp.json()
    assert [p["id"] for p in body["pending"]] == [waiting]
    assert body["pending"][0]["topic"] == "payments"
    assert [(r["id"], r["stars"], r["comment"]) for r in body["rated"]] == [
        (given, 4, "ok")
    ]
    assert still_open not in str(body) and theirs not in str(body)

    # Back at work: the given rating stays given, the waiting one waits no more.
    await _reopen(client, op, given)
    await _reopen(client, op, waiting)
    body = (await client.get(f"{_PERSON}/ratings", headers=person.headers)).json()
    assert body["pending"] == []
    assert [r["id"] for r in body["rated"]] == [given]


@pytest.mark.asyncio
async def test_nobody_rated_nothing_is_two_empty_lists(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    person = await _person(client, db_session)
    resp = await client.get(f"{_PERSON}/ratings", headers=person.headers)
    assert resp.json() == {"pending": [], "rated": []}
    assert (await client.get(f"{_PERSON}/ratings")).status_code == 401


# ---------------------------------------------------------------------------
# 4. The operator's row and card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_rating_is_in_the_list_row_and_the_card_alike(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session, language="ru")
    tid = await _ticket(client, person)
    await _close(client, op, tid)
    await _rate(client, person, tid, {"stars": 2, "comment": "долго"})

    card = (await client.get(f"{_STAFF}/tickets/{tid}", headers=op.headers)).json()
    rows = (
        await client.get(f"{_STAFF}/tickets", params={"limit": 100}, headers=op.headers)
    ).json()["items"]
    [row] = [r for r in rows if r["id"] == tid]
    assert row == card
    rating = card["rating"]
    assert (rating["stars"], rating["comment"], rating["comment_locale"]) == (
        2,
        "долго",
        "ru",
    )
    assert rating["rated_resolver"]["user_id"] == str(op.id)
    assert card["resolved_by"]["user_id"] == str(op.id)


@pytest.mark.asyncio
async def test_an_unrated_ticket_has_no_rating(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tid = await _ticket(client, person)
    card = (await client.get(f"{_STAFF}/tickets/{tid}", headers=op.headers)).json()
    assert (card["rating"], card["resolved_by"]) == (None, None)


@pytest.mark.asyncio
async def test_the_list_filters_by_rating(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    ids = [await _ticket(client, person) for _ in range(3)]
    five, two, none = ids
    for tid, stars in ((five, 5), (two, 2)):
        await _close(client, op, tid)
        await _rate(client, person, tid, {"stars": stars})

    async def listed(*ratings: str) -> set[str]:
        params = [("rating", r) for r in ratings] + [("limit", 100)]
        resp = await client.get(f"{_STAFF}/tickets", params=params, headers=op.headers)
        assert resp.status_code == 200, resp.text
        return {r["id"] for r in resp.json()["items"]} & set(ids)

    assert await listed("5") == {five}
    assert await listed("5", "2", "5") == {five, two}
    assert await listed("none") == {none}
    assert await listed("2", "none") == {two, none}
    assert await listed() == set(ids)
    for bad in ("6", "0", "x", "4.5"):
        resp = await client.get(f"{_STAFF}/tickets?rating={bad}", headers=op.headers)
        assert resp.status_code == 422, bad


# ---------------------------------------------------------------------------
# 5. The statistics
# ---------------------------------------------------------------------------


def _period() -> tuple[datetime, datetime]:
    """A day of its own, far in the past, for one test's tickets."""
    start = datetime(2001, 1, 1, tzinfo=UTC) + timedelta(days=uuid4().int % 3000)
    return start, start + timedelta(days=1)


async def _move(session: AsyncSession, tids: list[str], when: datetime) -> None:
    for i, tid in enumerate(tids):
        await session.execute(
            text(
                "UPDATE support_tickets SET created_at = :at WHERE support_thread_id = "
                "(SELECT id FROM support_threads WHERE comms_thread_id = :t)"
            ),
            {"at": when + timedelta(minutes=i + 1), "t": UUID(tid)},
        )
    await session.commit()


async def _stats(client: AsyncClient, op: Op, start: datetime, end: datetime) -> Any:
    return await client.get(
        f"{_STAFF}/stats",
        params={"created_from": start.isoformat(), "created_to": end.isoformat()},
        headers=op.headers,
    )


@pytest.mark.asyncio
async def test_the_categories_add_up_to_the_list_without_spam(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    tids = [
        await _ticket(client, person, topic=topic)
        for topic in ("kyc", "kyc", "payments", "technical", "other", "withdrawal")
    ]
    spam = await _ticket(client, person, topic="kyc")
    await _close(client, op, spam, "spam")
    await _close(client, op, tids[1], "rejected")
    start, end = _period()
    await _move(db_session, [*tids, spam], start)

    stats = (await _stats(client, op, start, end)).json()
    by = {c["category"]: c["tickets"] for c in stats["categories"]}
    assert [c["category"] for c in stats["categories"]] == list(CATEGORIES)
    assert by == {
        "payments": 1,
        "withdrawals": 1,
        "verification": 2,
        "purchases": 0,
        "tech": 1,
        "other": 1,
    }
    listed = (
        await client.get(
            f"{_STAFF}/tickets",
            params={
                "created_from": start.isoformat(),
                "created_to": end.isoformat(),
                "limit": 100,
            },
            headers=op.headers,
        )
    ).json()["items"]
    assert stats["total"]["tickets"] == sum(by.values()) == len(listed) == 6
    assert stats["spam"] == {"tickets": 1, "live": 1, "deleted": 0}


@pytest.mark.asyncio
async def test_ratings_by_category_and_by_whom_they_rated(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    ann = await _operator(client, db_session, comms)
    bob = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    plan = [("kyc", ann, 5), ("kyc", ann, 3), ("kyc", bob, 4), ("payments", bob, 2)]
    tids = []
    for topic, op, stars in plan:
        tid = await _ticket(client, person, topic=topic)
        await _close(client, op, tid)
        await _rate(client, person, tid, {"stars": stars})
        tids.append(tid)
    unrated = await _ticket(client, person, topic="payments")
    rated_spam = await _ticket(client, person, topic="kyc")
    await _close(client, ann, rated_spam)
    await _rate(client, person, rated_spam, {"stars": 1})
    await _reopen(client, ann, rated_spam)
    await _close(client, ann, rated_spam, "spam")
    start, end = _period()
    await _move(db_session, [*tids, unrated, rated_spam], start)

    stats = (await _stats(client, ann, start, end)).json()
    by = {c["category"]: c for c in stats["categories"]}
    assert (by["verification"]["tickets"], by["verification"]["rated"]) == (3, 3)
    assert by["verification"]["average"] == 4.0
    assert by["verification"]["share_4_5"] == 0.667
    assert (by["payments"]["tickets"], by["payments"]["rated"]) == (2, 1)
    assert (by["payments"]["average"], by["payments"]["share_4_5"]) == (2.0, 0.0)
    assert by["purchases"] == {
        "category": "purchases",
        "tickets": 0,
        "rated": 0,
        "average": None,
        "share_4_5": None,
    }
    assert stats["total"] == {
        "tickets": 5,
        "rated": 4,
        "average": 3.5,
        "share_4_5": 0.5,
    }
    resolvers = {r["operator"]["user_id"]: r for r in stats["resolvers"]}
    assert (resolvers[str(ann.id)]["rated"], resolvers[str(ann.id)]["average"]) == (
        2,
        4.0,
    )
    assert (resolvers[str(bob.id)]["rated"], resolvers[str(bob.id)]["average"]) == (
        2,
        3.0,
    )
    assert stats["spam"]["tickets"] == 1  # its rating counted nowhere


@pytest.mark.asyncio
async def test_spam_counts_the_tombstones_of_the_period(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    start, end = _period()
    for when in (start + timedelta(hours=1), start + timedelta(hours=23), end):
        db_session.add(SupportSpamTombstone(appealed_at=when, category="other"))
    await db_session.commit()
    stats = (await _stats(client, op, start, end)).json()
    assert stats["spam"] == {"tickets": 2, "live": 0, "deleted": 2}  # end excluded
    await db_session.execute(
        delete(SupportSpamTombstone).where(
            SupportSpamTombstone.appealed_at >= start,
            SupportSpamTombstone.appealed_at <= end,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_an_empty_period_lists_every_category_at_zero(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    start, end = _period()
    stats = (await _stats(client, op, start, end)).json()
    assert [
        (c["category"], c["tickets"], c["rated"], c["average"])
        for c in stats["categories"]
    ] == [(category, 0, 0, None) for category in CATEGORIES]
    assert stats["total"] == {
        "tickets": 0,
        "rated": 0,
        "average": None,
        "share_4_5": None,
    }
    assert stats["spam"]["tickets"] == 0
    assert stats["resolvers"] == []


@pytest.mark.asyncio
async def test_the_period_ends_before_created_to(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    person = await _person(client, db_session)
    inside = await _ticket(client, person, topic="other")
    on_the_edge = await _ticket(client, person, topic="other")
    start, end = _period()
    await _move(db_session, [inside], start)
    await db_session.execute(
        text(
            "UPDATE support_tickets SET created_at = :at WHERE support_thread_id = "
            "(SELECT id FROM support_threads WHERE comms_thread_id = :t)"
        ),
        {"at": end, "t": UUID(on_the_edge)},
    )
    await db_session.commit()
    stats = (await _stats(client, op, start, end)).json()
    assert {c["category"]: c["tickets"] for c in stats["categories"]}["other"] == 1
    # The same edge, read in another zone, is the same instant.
    plus3 = timezone(timedelta(hours=3))
    again = (
        await _stats(client, op, start.astimezone(plus3), end.astimezone(plus3))
    ).json()
    assert again["categories"] == stats["categories"]


@pytest.mark.asyncio
async def test_the_period_is_two_zoned_edges_in_order(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    op = await _operator(client, db_session, comms)
    start, end = _period()
    naive = start.replace(tzinfo=None).isoformat()
    for params, status, code in (
        ({"created_from": start.isoformat()}, 422, None),
        ({"created_to": end.isoformat()}, 422, None),
        (
            {"created_from": naive, "created_to": end.isoformat()},
            400,
            "support_date_without_zone",
        ),
        (
            {"created_from": end.isoformat(), "created_to": start.isoformat()},
            400,
            "support_period_empty",
        ),
        (
            {"created_from": start.isoformat(), "created_to": start.isoformat()},
            400,
            "support_period_empty",
        ),
    ):
        resp = await client.get(f"{_STAFF}/stats", params=params, headers=op.headers)
        assert resp.status_code == status, (params, resp.text)
        if code is not None:
            assert resp.json()["error"] == code


@pytest.mark.asyncio
async def test_statistics_are_for_operators(
    client: AsyncClient, db_session: AsyncSession, comms: FakeComms
) -> None:
    person = await _person(client, db_session)
    start, end = _period()
    params = {"created_from": start.isoformat(), "created_to": end.isoformat()}
    resp = await client.get(f"{_STAFF}/stats", params=params, headers=person.headers)
    assert resp.status_code == 403
    assert (await client.get(f"{_STAFF}/stats", params=params)).status_code == 401
