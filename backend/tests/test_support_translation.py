# =============================================================================
# AIVIS.ONE Backend -- support translation through comms variants and the
# comms push listener (H39 P-129)
# =============================================================================
#
# comms is a FAKE here (FakeComms): one stateful stand-in behind every seam
# the code reaches comms through -- the support service, the translation
# module, the llm client and the listener. It keeps the thread's messages,
# the llm jobs (a job exists for comms only once the test SHIPS it from the
# outbox -- comms takes jobs asynchronously), the variant requests and the
# variants, and decides the feed's variant_state by comms
# deploy/INTEGRATION.md section 12's table. It refuses what comms refuses,
# in comms' classes: a request naming a job it does not have (422
# validation), a variant from a job without an answer (422), a second
# variant in a language (409 conflict).
#
# The mechanism is velo's (BE-166); the grid of these tests is the H39
# handoff's section 8, plus the three axes of every input touched.
# =============================================================================

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import structlog
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import comms_listener
from app.core.comms import (
    CLASS_CURSOR_EXPIRED,
    CommsRejectedError,
    CommsUnavailableError,
)
from app.core.config import Settings, settings
from app.core.database import get_engine
from app.core.events.models import CommsFeedCursor, OutboxEvent
from app.core.events.relay import LLM_LETTER_REDACTED, relay_pending_batch
from app.core.events.service import EVENT_NOTIFICATION_REQUEST, emit_event
from app.core.llm import LlmResult, decide, enqueue_llm_job
from app.modules.support import translation
from app.modules.support.models import SupportThread, SupportTranslationJob
from app.modules.users.models import User
from tests.helpers import auth_headers, create_staff_user, register_user

_SEAMS = (
    "app.modules.support.service.comms_request",
    "app.modules.support.translation.comms_request",
    "app.core.llm.comms_request",
    "app.core.comms_listener.comms_request",
)

_CLIENT_BASE = "/api/v1/support/threads"
_STAFF_BASE = "/api/v1/staff/support/threads"


# ---------------------------------------------------------------------------
# The fake comms
# ---------------------------------------------------------------------------


def _refuse(status: int, error_class: str) -> CommsRejectedError:
    return CommsRejectedError(status_code=status, error_class=error_class)


class FakeComms:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []  # oldest first
        self.jobs: dict[str, dict[str, Any]] = {}
        self.requests: list[tuple[str, str, str]] = []  # (mid, locale, job)
        self.variants: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[tuple[str, str, Any, dict, str | None]] = []
        self.changes: list[str] = []
        self.keys: dict[Any, Any] = {}
        self.down = False
        self.cursor_expired_once = False

    # -- what the tests do to it --
    def answer(self, key: str, content: str, finish: str = "stop") -> None:
        body = {"choices": [{"finish_reason": finish, "message": {"content": content}}]}
        self.jobs[key] |= {"status": "sent", "answer": json.dumps(body)}

    def fail(self, key: str, status: str = "failed") -> None:
        self.jobs[key] |= {"status": status, "answer": None}

    def count(self, method: str, suffix: str) -> int:
        return sum(1 for c in self.calls if c[0] == method and c[1].endswith(suffix))

    # -- comms --
    def _state(self, mid: str, locale: str) -> str:
        own = self.variants.get((mid, locale))
        if own is not None:
            if own["declined"]:
                return "impossible"
            return "ready" if own["body"] else "not_needed"
        if any(
            m == mid and v["source_locale"] == locale
            for (m, _), v in self.variants.items()
        ):
            return "not_needed"
        mine = [r for r in self.requests if r[0] == mid and r[1] == locale]
        if mine:
            status = self.jobs[mine[-1][2]]["status"]
            return (
                "impossible"
                if status in ("failed", "expired", "cancelled")
                else "preparing"
            )
        return "not_requested"

    async def __call__(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        forward_403: bool = False,
        idempotency_key: str | None = None,
        forward_cursor_expired: bool = False,
    ) -> Any:
        params = dict(params or {})
        self.calls.append((method, path, json, params, idempotency_key))
        if self.down:
            raise CommsUnavailableError()
        if idempotency_key is not None and (method, path, idempotency_key) in self.keys:
            return self.keys[(method, path, idempotency_key)]
        result = self._route(method, path, params, json, forward_cursor_expired)
        if idempotency_key is not None:
            self.keys[(method, path, idempotency_key)] = result
        return result

    def _route(
        self,
        method: str,
        path: str,
        params: dict,
        body: dict | None,
        forward_cursor_expired: bool,
    ) -> Any:
        parts = path.strip("/").split("/")
        if path == "/api/v1/notifications/by-key":
            job = self.jobs.get(params["key"])
            if job is None:
                raise _refuse(404, "not_found")
            if job.get("intake_rejected"):
                return {
                    "idempotency_key": params["key"],
                    "intake": [{"outcome": "rejected_at_intake", "reason": "x"}],
                    "job": None,
                }
            answer = (
                {"state": "kept", "body": job["answer"]}
                if job.get("answer") is not None
                else None
            )
            return {"job": {"status": job["status"], "answer": answer}}
        if path == "/api/v1/notifications/changes":
            if self.cursor_expired_once and params.get("cursor") is not None:
                self.cursor_expired_once = False
                assert forward_cursor_expired, "410 must be opted into"
                raise _refuse(410, CLASS_CURSOR_EXPIRED)
            cursor = int(params.get("cursor") or 0)
            items = self.changes[cursor : cursor + params.get("limit", 100)]
            return {
                "items": [{"idempotency_key": k} for k in items],
                "next_cursor": str(cursor + len(items)),
            }
        if parts[:3] == ["api", "v1", "threads"] and len(parts) == 5:
            if method == "POST":
                message = {
                    "id": str(uuid4()),
                    "thread_id": parts[3],
                    "sender": body["sender"],
                    "body": body["body"],
                    "created_at": datetime.now(UTC).isoformat(),
                }
                self.messages.append(message)
                return message
            newest = [m for m in reversed(self.messages) if m["thread_id"] == parts[3]]
            start = int(params.get("cursor") or 0)
            page = newest[start : start + params.get("limit", 20)]
            nxt = str(start + len(page)) if start + len(page) < len(newest) else None
            locale = params.get("locale")
            items = []
            for m in page:
                item = dict(m)
                if locale is not None:
                    state = self._state(m["id"], locale)
                    v = self.variants.get((m["id"], locale))
                    item["variant_state"] = state
                    item["variant"] = (
                        {
                            "locale": locale,
                            "source_locale": v["source_locale"],
                            "body": v["body"],
                        }
                        if state == "ready"
                        else None
                    )
                items.append(item)
            return {"items": items, "next_cursor": nxt}
        if parts[-1] == "variant-requests":
            mid = parts[5]
            job = self.jobs.get(body["job_key"])
            if job is None or job.get("intake_rejected"):
                # comms keeps no job for a request it refused at intake.
                raise _refuse(422, "validation")
            self.requests.append((mid, body["locale"], body["job_key"]))
            return {"message_id": mid, **body}
        if parts[-1] == "variants":
            mid = parts[5]
            job = self.jobs.get(body["job_key"])
            if job is None or job.get("answer") is None:
                raise _refuse(422, "validation")
            if (mid, body["locale"]) in self.variants:
                raise _refuse(409, "conflict")
            self.variants[(mid, body["locale"])] = {
                "source_locale": body.get("source_locale"),
                "body": body.get("body"),
                "declined": body.get("declined", False),
            }
            return {"message_id": mid, **body}
        raise AssertionError(f"unexpected comms call {method} {path}")


async def ship(session: AsyncSession, fake: FakeComms) -> list[dict]:
    """What the relay and comms' intake would do: every llm job of THIS
    fake's messages in the outbox becomes a job comms knows. Returns the
    shipped payloads."""
    session.expire_all()
    rows = (
        (
            await session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.payload["idempotency_key"].astext.like(
                        f"{translation.JOB_PREFIX}%",
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    mids = {m["id"] for m in fake.messages}
    shipped = []
    for row in rows:
        key = row.payload["idempotency_key"]
        parsed = translation.parse_job_key(key)
        if parsed is None or str(parsed[0]) not in mids or key in fake.jobs:
            continue
        fake.jobs[key] = {"status": "pending", "answer": None, "payload": row.payload}
        shipped.append(row.payload)
    return shipped


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeComms:
    comms = FakeComms()
    for seam in _SEAMS:
        monkeypatch.setattr(seam, comms)
    monkeypatch.setattr(settings, "support_language", "en")
    return comms


async def _clean(session: AsyncSession) -> None:
    # The queue is test residue between tests (other support suites write
    # it too); the listener's passes read the WHOLE queue, so each test
    # starts from an empty one.
    await session.execute(delete(SupportTranslationJob))
    await session.execute(
        delete(OutboxEvent).where(
            OutboxEvent.payload["idempotency_key"].astext.like("aivis:llm-support-tr:%")
            | OutboxEvent.payload["idempotency_key"].astext.like("aivis:support-tr-%")
        )
    )
    await session.execute(delete(CommsFeedCursor))
    await session.commit()


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    await _clean(db_session)
    yield
    await _clean(db_session)


class Setup:
    def __init__(
        self,
        *,
        person_token: str,
        person_id: UUID,
        staff_token: str,
        thread_id: UUID,
        pointer_id: UUID,
    ) -> None:
        self.person_token = person_token
        self.person_id = person_id
        self.staff_token = staff_token
        self.thread_id = thread_id
        self.pointer_id = pointer_id


async def _setup(
    client: AsyncClient, db_session: AsyncSession, *, language: str,
) -> Setup:
    """A person reading `language`, an operator, and the person's pointer."""
    person = await register_user(client)
    person_id = UUID(person["user"]["id"])
    await db_session.execute(
        update(User).where(User.id == person_id).values(language=language)
    )
    pointer = SupportThread(user_id=person_id, comms_thread_id=uuid4())
    db_session.add(pointer)
    await db_session.commit()
    _, staff_token = await create_staff_user(client, db_session)
    return Setup(
        person_token=person["session_token"],
        person_id=person_id,
        staff_token=staff_token,
        thread_id=pointer.comms_thread_id,
        pointer_id=pointer.id,
    )


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


async def _person_writes(client: AsyncClient, s: Setup, body: str) -> dict:
    resp = await client.post(
        f"{_CLIENT_BASE}/messages",
        json={"body": body},
        headers={**auth_headers(s.person_token), **_key()},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _staff_replies(client: AsyncClient, s: Setup, body: str) -> dict:
    resp = await client.post(
        f"{_STAFF_BASE}/{s.thread_id}/messages",
        json={"body": body},
        headers={**auth_headers(s.staff_token), **_key()},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _staff_feed(client: AsyncClient, s: Setup) -> dict[str, dict]:
    resp = await client.get(
        f"{_STAFF_BASE}/{s.thread_id}/messages",
        headers=auth_headers(s.staff_token),
    )
    assert resp.status_code == 200, resp.text
    return {m["id"]: m for m in resp.json()["items"]}


async def _person_feed(client: AsyncClient, s: Setup) -> dict[str, dict]:
    resp = await client.get(
        f"{_CLIENT_BASE}/{s.thread_id}/messages",
        headers=auth_headers(s.person_token),
    )
    assert resp.status_code == 200, resp.text
    return {m["id"]: m for m in resp.json()["items"]}


def _retry_url(s: Setup, mid: str) -> str:
    return f"{_STAFF_BASE}/{s.thread_id}/messages/{mid}/translation/retry"


class Row:
    """A row's values, read once: an ORM row would expire under the tests'
    own expire_all and lazy-load outside the async context."""

    def __init__(self, row: SupportTranslationJob) -> None:
        self.direction = row.direction
        self.locale = row.locale
        self.attempt = row.attempt
        self.outcome = row.outcome
        self.job_key = row.job_key
        self.request_written_at = row.request_written_at
        self.user_notified_at = row.user_notified_at


async def _rows(session: AsyncSession, message_id: str) -> list[Row]:
    session.expire_all()
    rows = (
        (
            await session.execute(
                select(SupportTranslationJob)
                .where(SupportTranslationJob.comms_message_id == UUID(message_id))
                .order_by(SupportTranslationJob.attempt)
            )
        )
        .scalars()
        .all()
    )
    return [Row(r) for r in rows]


async def _notices(session: AsyncSession, message_id: str) -> list[dict]:
    session.expire_all()
    rows = (
        (
            await session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.payload["type"].astext == translation.UNAVAILABLE_TYPE,
                    OutboxEvent.payload["idempotency_key"].astext.like(
                        f"aivis:support-tr-unavailable:{message_id}:%",
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    return [r.payload for r in rows]


def _answer(source: str, text_: str | None, declined: bool = False) -> str:
    return json.dumps(
        {"source_language": source, "translation": text_, "declined": declined},
    )


def _no_text_in(logs: list[dict], *texts: str) -> None:
    # The pair: the logs were captured -- the path logged its own events
    # (by key, never by text) -- so "no text in them" is a measurement.
    events = {entry.get("event") for entry in logs}
    assert {"support_translation_queued", "support_translation_outcome"} <= events, events
    flat = json.dumps(logs, default=str)
    for text_ in texts:
        assert text_ not in flat, f"{text_!r} reached a log line"


# ---------------------------------------------------------------------------
# 1. The whole path, both directions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_persons_message_goes_in_at_once_and_its_translation_follows(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    with structlog.testing.capture_logs() as logs:
        sent = await _person_writes(client, s, "Ich kann mich nicht anmelden")
        mid = sent["id"]

        # In the thread AS WRITTEN, before any model is asked.
        assert [m["body"] for m in fake.messages] == ["Ich kann mich nicht anmelden"]
        [row] = await _rows(db_session, mid)
        assert (row.direction, row.locale, row.attempt, row.outcome) == (
            "to_support", "en", 1, None,
        )

        # The request waits for comms to take the job: 422 until shipped.
        await translation.sweep()
        assert fake.count("POST", "/variant-requests") == 1 and fake.requests == []
        [row] = await _rows(db_session, mid)
        assert row.request_written_at is None and row.outcome is None
        # Meanwhile the staff feed says the translation is on its way.
        assert (await _staff_feed(client, s))[mid]["translation"]["state"] == "preparing"

        [payload] = await ship(db_session, fake)
        assert payload["type"] == translation.FOR_SUPPORT_TYPE
        system, letter = payload["llm"]["messages"]
        assert letter == {"role": "user", "content": "Ich kann mich nicht anmelden"}
        assert "English (en)" in system["content"]
        await translation.sweep()
        assert fake.requests == [(mid, "en", row.job_key)]

        fake.answer(row.job_key, _answer("de", "I cannot log in"))
        await translation.on_key(row.job_key)
        assert fake.variants[(mid, "en")] == {
            "source_locale": "de", "body": "I cannot log in", "declined": False,
        }
        seen = (await _staff_feed(client, s))[mid]
        assert seen["body"] == "I cannot log in"
        assert seen["original"] == "Ich kann mich nicht anmelden"
        assert seen["translation"] == {
            "locale": "en", "state": "ready", "source_locale": "de", "retryable": False,
        }
        [row] = await _rows(db_session, mid)
        assert row.outcome == "variant"

        # The person reads their own words, as written.
        mine = (await _person_feed(client, s))[mid]
        assert mine["body"] == "Ich kann mich nicht anmelden" and mine["translation"] is None

    _no_text_in(logs, "anmelden", "log in")


@pytest.mark.asyncio
async def test_a_staff_reply_reaches_the_person_only_in_their_language(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    with structlog.testing.capture_logs() as logs:
        sent = await _staff_replies(client, s, "Please reset your password")
        mid = sent["id"]
        assert sent["body"] == "Please reset your password"  # comms' message
        [row] = await _rows(db_session, mid)
        assert (row.direction, row.locale) == ("to_user", "de")

        # Before the translation: the person gets NO text, a state.
        theirs = (await _person_feed(client, s))[mid]
        assert theirs["body"] is None and theirs["translation"] == "translating"
        assert "Please reset" not in json.dumps(theirs)

        [payload] = await ship(db_session, fake)
        assert payload["type"] == translation.FOR_USER_TYPE
        assert "German (de)" in payload["llm"]["messages"][0]["content"]
        await translation.sweep()
        fake.answer(row.job_key, _answer("en", "Bitte setzen Sie Ihr Passwort zurück"))
        await translation.on_key(row.job_key)

        theirs = (await _person_feed(client, s))[mid]
        assert theirs == {
            "id": mid,
            "thread_id": str(s.thread_id),
            "sender": sent["sender"],
            "created_at": sent["created_at"],
            "body": "Bitte setzen Sie Ihr Passwort zurück",
            "translation": None,
        }
        seen = (await _staff_feed(client, s))[mid]
        assert seen["body"] == "Please reset your password"  # the operator's own
        assert seen["translation"]["variant_body"] == "Bitte setzen Sie Ihr Passwort zurück"
        assert seen["translation"]["state"] == "ready"

    _no_text_in(logs, "reset your password", "Passwort")


@pytest.mark.asyncio
async def test_a_reply_to_a_person_of_the_support_language_queues_nothing(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    """The pair: the reply goes in, and NO job exists for it -- while the
    person's own message is still always translated."""
    s = await _setup(client, db_session, language="EN-us")  # normalized: en
    sent = await _staff_replies(client, s, "Hello")
    assert await _rows(db_session, sent["id"]) == []
    theirs = (await _person_feed(client, s))[sent["id"]]
    assert theirs["body"] == "Hello" and theirs["translation"] is None
    assert (await _staff_feed(client, s))[sent["id"]]["translation"] is None

    own = await _person_writes(client, s, "Hi there")
    [row] = await _rows(db_session, own["id"])
    assert (row.direction, row.locale) == ("to_support", "en")


@pytest.mark.asyncio
async def test_a_message_already_in_the_support_language_is_marked_not_needed(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="ru")
    sent = await _person_writes(client, s, "I wrote in English anyway")
    [row] = await _rows(db_session, sent["id"])
    await ship(db_session, fake)
    fake.answer(row.job_key, _answer("en", None))
    await translation.on_key(row.job_key)

    assert fake.variants[(sent["id"], "en")] == {
        "source_locale": "en", "body": None, "declined": False,
    }
    [row] = await _rows(db_session, sent["id"])
    assert row.outcome == "not_needed"
    seen = (await _staff_feed(client, s))[sent["id"]]
    assert seen["body"] == seen["original"] == "I wrote in English anyway"
    assert seen["translation"]["state"] == "not_needed"


# ---------------------------------------------------------------------------
# 2. When it does not work out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_declined_reply_tells_the_person_once_and_is_final(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="ru")
    sent = await _staff_replies(client, s, "Untranslatable")
    mid = sent["id"]
    [row] = await _rows(db_session, mid)
    await ship(db_session, fake)
    fake.answer(row.job_key, _answer("en", None, declined=True))
    await translation.on_key(row.job_key)
    await translation.on_key(row.job_key)  # a repeated push: nothing more

    assert fake.variants[(mid, "ru")]["declined"] is True
    assert fake.count("POST", "/variants") == 1
    [row] = await _rows(db_session, mid)
    assert row.outcome == "declined" and row.user_notified_at is not None
    [notice] = await _notices(db_session, mid)
    assert notice["target_value"] == str(s.person_id)
    assert notice["title"] == "Ответ поддержки не переведён"  # the person reads ru
    assert "Untranslatable" not in json.dumps(notice)

    theirs = (await _person_feed(client, s))[mid]
    assert theirs["body"] is None and theirs["translation"] == "unavailable"
    seen = (await _staff_feed(client, s))[mid]
    assert seen["translation"]["state"] == "impossible"
    assert seen["translation"]["retryable"] is False

    # Final in comms: no retry after declined.
    resp = await client.post(_retry_url(s, mid), headers=auth_headers(s.staff_token))
    assert resp.status_code == 409, resp.text
    assert len(await _rows(db_session, mid)) == 1


@pytest.mark.asyncio
async def test_an_unreadable_answer_is_asked_again_once_then_declined(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    sent = await _staff_replies(client, s, "Two tries")
    mid = sent["id"]
    [first] = await _rows(db_session, mid)
    await ship(db_session, fake)
    await translation.sweep()
    fake.answer(first.job_key, "this is not json")
    await translation.on_key(first.job_key)

    first, second = await _rows(db_session, mid)
    assert (first.outcome, second.attempt, second.outcome) == ("retried", 2, None)
    assert await _notices(db_session, mid) == []  # not told yet: asked again
    [payload] = await ship(db_session, fake)
    assert payload["llm"]["messages"][1]["content"] == "Two tries"  # read back

    fake.answer(second.job_key, "still not json", finish="length")
    await translation.on_key(second.job_key)
    first, second = await _rows(db_session, mid)
    assert second.outcome == "declined"
    assert fake.variants[(mid, "de")]["declined"] is True
    assert len(await _notices(db_session, mid)) == 1


@pytest.mark.asyncio
async def test_a_transport_failure_is_retryable_by_staff_and_told_once(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    sent = await _staff_replies(client, s, "Lost on the way")
    mid = sent["id"]
    [row] = await _rows(db_session, mid)

    # Retry while it is still running: nothing to retry.
    resp = await client.post(_retry_url(s, mid), headers=auth_headers(s.staff_token))
    assert resp.status_code == 409, resp.text

    await ship(db_session, fake)
    await translation.sweep()
    fake.fail(row.job_key, "expired")
    await translation.on_key(row.job_key)

    [row] = await _rows(db_session, mid)
    assert row.outcome == "failed"
    assert (mid, "de") not in fake.variants  # no variant: comms says impossible
    assert len(await _notices(db_session, mid)) == 1
    seen = (await _staff_feed(client, s))[mid]
    assert seen["translation"]["state"] == "impossible"
    assert seen["translation"]["retryable"] is True

    resp = await client.post(_retry_url(s, mid), headers=auth_headers(s.staff_token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["attempt"] == 2
    again = await client.post(_retry_url(s, mid), headers=auth_headers(s.staff_token))
    assert again.status_code == 409, again.text  # attempt 2 is in progress

    _, second = await _rows(db_session, mid)
    await ship(db_session, fake)
    await translation.sweep()
    fake.fail(second.job_key)
    await translation.on_key(second.job_key)
    assert len(await _notices(db_session, mid)) == 1  # still once


@pytest.mark.asyncio
async def test_a_job_refused_at_intake_is_a_failure_without_a_request(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    sent = await _person_writes(client, s, "Refused")
    [row] = await _rows(db_session, sent["id"])
    await ship(db_session, fake)
    fake.jobs[row.job_key]["intake_rejected"] = True

    await translation.sweep()  # 422 -> the job is read -> over
    [row] = await _rows(db_session, sent["id"])
    assert row.outcome == "failed" and row.request_written_at is None
    assert fake.requests == []
    # A person's message: staff are not "told", they see it in the feed.
    assert await _notices(db_session, sent["id"]) == []


@pytest.mark.asyncio
async def test_comms_down_while_writing_the_variant_leaves_the_row_open(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    sent = await _person_writes(client, s, "Later")
    [row] = await _rows(db_session, sent["id"])
    await ship(db_session, fake)
    fake.answer(row.job_key, _answer("de", "Later, in English"))

    # comms goes away between reading the answer and writing the variant:
    # the outcome is not recorded, and the next pass reads the job again.
    original = fake._route

    def failing(method, path, params, body, fce):  # type: ignore[no-untyped-def]
        if path.endswith("/variants"):
            raise CommsUnavailableError()
        return original(method, path, params, body, fce)

    fake._route = failing  # type: ignore[method-assign]
    with pytest.raises(CommsUnavailableError):
        await translation.on_key(row.job_key)
    [row] = await _rows(db_session, sent["id"])
    assert row.outcome is None

    fake._route = original  # type: ignore[method-assign]
    await translation.resume()
    [row] = await _rows(db_session, sent["id"])
    assert row.outcome == "variant"


# ---------------------------------------------------------------------------
# 3. The catch-up, and the axes of the send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feeds_queue_what_nobody_asked_for(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    """A message whose job was lost (comms took it, our commit did not) is
    queued by the next read of a feed that shows it -- once."""
    s = await _setup(client, db_session, language="de")
    lost_person = {
        "id": str(uuid4()), "thread_id": str(s.thread_id),
        "sender": str(s.person_id), "body": "lost one",
        "created_at": datetime.now(UTC).isoformat(),
    }
    lost_reply = {
        "id": str(uuid4()), "thread_id": str(s.thread_id),
        "sender": str(uuid4()), "body": "lost reply",
        "created_at": datetime.now(UTC).isoformat(),
    }
    fake.messages += [lost_person, lost_reply]

    theirs = (await _person_feed(client, s))[lost_reply["id"]]
    assert theirs["body"] is None and theirs["translation"] == "translating"
    [reply_row] = await _rows(db_session, lost_reply["id"])
    assert reply_row.direction == "to_user" and reply_row.locale == "de"
    # The person's feed does not queue the person's own message.
    assert await _rows(db_session, lost_person["id"]) == []

    await _staff_feed(client, s)
    await _staff_feed(client, s)  # a second read queues nothing more
    [person_row] = await _rows(db_session, lost_person["id"])
    assert person_row.direction == "to_support"
    assert len(await _rows(db_session, lost_reply["id"])) == 1


@pytest.mark.asyncio
async def test_a_send_retried_under_its_key_queues_one_job(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    key = _key()
    for _ in range(2):
        resp = await client.post(
            f"{_CLIENT_BASE}/messages",
            json={"body": "once"},
            headers={**auth_headers(s.person_token), **key},
        )
        assert resp.status_code == 200, resp.text
    [message] = fake.messages
    assert len(await _rows(db_session, message["id"])) == 1


@pytest.mark.asyncio
async def test_a_sent_message_without_an_id_queues_nothing(
    db_session: AsyncSession, fake: FakeComms,
) -> None:
    pointer = SupportThread(id=uuid4(), user_id=uuid4(), comms_thread_id=uuid4())
    for answer in ({}, {"id": None}, {"id": "not-a-uuid"}, "not a dict"):
        await translation.enqueue_for_sent(
            db_session,
            pointer=pointer,
            message=answer,
            direction="to_support",
            locale="en",
            text="x",
        )
    session_rows = (
        await db_session.execute(select(func.count()).select_from(SupportTranslationJob))
    ).scalar_one()
    assert session_rows == 0
    await db_session.rollback()


@pytest.mark.asyncio
async def test_retry_of_a_message_out_of_reach_is_404_and_of_a_same_language_reply_409(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="en")
    resp = await client.post(
        _retry_url(s, str(uuid4())), headers=auth_headers(s.staff_token),
    )
    assert resp.status_code == 404, resp.text
    sent = await _staff_replies(client, s, "same language")
    resp = await client.post(_retry_url(s, sent["id"]), headers=auth_headers(s.staff_token))
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# 4. What the person may read -- the fail-closed grid (pure)
# ---------------------------------------------------------------------------

_CLIENT = "11111111-1111-4111-8111-111111111111"
_STAFF = "22222222-2222-4222-8222-222222222222"


def _item(**over: Any) -> dict[str, Any]:
    base = {
        "id": "m", "thread_id": "t", "sender": _STAFF, "body": "ORIGINAL",
        "created_at": "now",
    }
    return base | over


@pytest.mark.parametrize(
    ("item", "locale", "body", "state"),
    [
        (_item(sender=_CLIENT), "de", "ORIGINAL", None),  # own message
        (_item(), None, "ORIGINAL", None),  # reads the support language
        (
            _item(variant_state="ready", variant={"locale": "de", "body": "Text"}),
            "de", "Text", None,
        ),
        (_item(variant_state="not_needed"), "de", "ORIGINAL", None),
        (_item(variant_state="preparing"), "de", None, "translating"),
        (_item(variant_state="not_requested"), "de", None, "translating"),
        (_item(variant_state="impossible"), "de", None, "unavailable"),
        (_item(variant_state="something_new"), "de", None, "unavailable"),
        (_item(), "de", None, "unavailable"),  # no state at all
        (_item(variant_state="ready", variant=None), "de", None, "unavailable"),
        (
            _item(variant_state="ready", variant={"locale": "fr", "body": "Texte"}),
            "de", None, "unavailable",
        ),
        (
            _item(variant_state="ready", variant={"locale": "de", "body": "  "}),
            "de", None, "unavailable",
        ),
    ],
)
def test_the_person_never_gets_the_original_of_a_reply_in_another_language(
    item: dict, locale: str | None, body: str | None, state: str | None,
) -> None:
    out = translation.render_for_client(item, client_id=_CLIENT, user_locale=locale)
    assert out is not None
    assert (out["body"], out["translation"]) == (body, state)
    assert "variant" not in out and "variant_state" not in out
    if body != "ORIGINAL":
        assert "ORIGINAL" not in json.dumps(out)


def test_a_feed_item_that_is_not_an_object_is_dropped() -> None:
    for junk in (None, "x", 1, ["ORIGINAL"]):
        assert translation.render_for_client(junk, client_id=_CLIENT, user_locale="de") is None


# ---------------------------------------------------------------------------
# 5. The parses (pure)
# ---------------------------------------------------------------------------


def _llm(text_: str) -> LlmResult:
    return LlmResult("answer", text=text_)


@pytest.mark.parametrize(
    ("result", "kind", "source"),
    [
        (_llm(_answer("de", "Hello")), "text", "de"),
        (_llm("```json\n" + _answer("de-DE", "Hello") + "\n```"), "text", "de"),
        (_llm(_answer("EN", None)), "not_needed", "en"),
        (_llm(_answer("de", None, declined=True)), "declined", "de"),
        (_llm(_answer("en", None, declined=True)), "declined", None),
        (_llm(json.dumps({"source_language": "de", "declined": "yes"})), "unreadable", None),
        (_llm("not json"), "unreadable", None),
        (_llm("[1, 2]"), "unreadable", None),
        (_llm(_answer("", "Hello")), "unreadable", None),
        (_llm(json.dumps({"translation": "Hello"})), "unreadable", None),
        (_llm(_answer("de", "   ")), "unreadable", None),
        (_llm(_answer("de", None)), "unreadable", None),
        (_llm(_answer("de", "x" * 5001)), "unreadable", None),
        (LlmResult("failed", reason="status_failed"), "failed", None),
        (LlmResult("in_progress"), "in_progress", None),
    ],
)
def test_parse_translation_grid(result: LlmResult, kind: str, source: str | None) -> None:
    outcome = translation.parse_translation(result, "en")
    assert outcome.kind == kind
    assert outcome.source_locale == source


def _chat(content: Any, finish: str = "stop") -> str:
    return json.dumps({"choices": [{"finish_reason": finish, "message": {"content": content}}]})


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        ({"job": {"status": "sent", "answer": {"state": "kept", "body": _chat("ok")}}}, "answer"),
        ({"job": {"status": "pending"}}, "in_progress"),
        ({"job": {"status": "processing"}}, "in_progress"),
        ({"job": None, "intake": []}, "in_progress"),
        ({"job": None, "intake": [{"outcome": "rejected_at_intake"}]}, "failed"),
        ({"job": {"status": "failed"}}, "failed"),
        ({"job": {"status": "expired"}}, "failed"),
        ({"job": {"status": "cancelled"}}, "failed"),
        ({"job": {"status": "something_new"}}, "failed"),
        ({"job": "x"}, "failed"),
        ("not a dict", "failed"),
        ({"job": {"status": "sent", "answer": None}}, "unreadable"),
        ({"job": {"status": "sent", "answer": {"state": "purged"}}}, "unreadable"),
        ({"job": {"status": "sent", "answer": {"state": "kept", "body": "{"}}}, "unreadable"),
        ({"job": {"status": "sent", "answer": {"state": "kept", "body": _chat("ok", "length")}}}, "unreadable"),
        ({"job": {"status": "sent", "answer": {"state": "kept", "body": _chat("  ")}}}, "unreadable"),
        ({"job": {"status": "sent", "answer": {"state": "kept", "body": json.dumps({"choices": []})}}}, "unreadable"),
    ],
)
def test_decide_grid(payload: Any, kind: str) -> None:
    assert decide(payload).kind == kind


@pytest.mark.parametrize(
    ("value", "expected"),
    [("en", "en"), ("EN", "en"), ("en-US", "en"), ("ru_RU", "ru"), ("de", "de"),
     ("", "en"), ("   ", "en"), ("deu", "en"), ("中文", "en"), (None, "en")],
)
def test_users_language_is_read_not_trusted(value: Any, expected: str) -> None:
    assert translation.normalize_language(value) == expected


def test_job_keys_round_trip_and_stay_within_comms_bound() -> None:
    mid = uuid4()
    key = translation.job_key(mid, "de", 2)
    assert translation.parse_job_key(key) == (mid, "de", 2)
    assert len(key) <= 200
    for junk in ("", "other:key", f"{translation.JOB_PREFIX}x:de:1", f"{translation.JOB_PREFIX}{mid}:de"):
        assert translation.parse_job_key(junk) is None


@pytest.mark.asyncio
async def test_an_llm_key_outside_comms_bound_is_refused(db_session: AsyncSession) -> None:
    for key in ("", "k" * 201):
        with pytest.raises(ValueError):
            await enqueue_llm_job(
                db_session, idempotency_key=key, type="t",
                messages=[{"role": "user", "content": "x"}],
            )
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 6. The listener
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self.acked: list[Any] = []

    async def xack(self, stream: str, group: str, entry_id: Any) -> None:
        self.acked.append(entry_id)


@pytest.mark.asyncio
async def test_the_stream_reads_then_acknowledges_and_ignores_foreign_keys(
    client: AsyncClient, db_session: AsyncSession, fake: FakeComms,
) -> None:
    s = await _setup(client, db_session, language="de")
    sent = await _person_writes(client, s, "Push me")
    [row] = await _rows(db_session, sent["id"])
    await ship(db_session, fake)
    fake.answer(row.job_key, _answer("de", "Pushed"))
    redis = FakeRedis()
    calls_before = len(fake.calls)

    await comms_listener.process_entries(
        redis,  # type: ignore[arg-type]
        [
            (b"1-0", {b"v": b"1", b"idempotency_key": b"tranche-paid:x"}),  # not ours
            (b"2-0", {b"v": b"1"}),  # no key at all
            (b"3-0", {b"v": b"1", b"idempotency_key": row.job_key.encode()}),
            (b"4-0", {b"v": b"1", b"idempotency_key": row.job_key.encode()}),  # repeat
        ],
    )
    assert redis.acked == [b"1-0", b"2-0", b"3-0", b"4-0"]
    # Only our key was read, and its outcome applied once.
    reads = [c for c in fake.calls[calls_before:] if c[1].endswith("/by-key")]
    assert {c[3]["key"] for c in reads} == {row.job_key}
    assert fake.count("POST", "/variants") == 1
    [row] = await _rows(db_session, sent["id"])
    assert row.outcome == "variant"


@pytest.mark.asyncio
async def test_a_push_of_an_unknown_format_stops_unacknowledged() -> None:
    redis = FakeRedis()
    for fields in ({b"v": b"2", b"idempotency_key": b"k"}, {b"idempotency_key": b"k"}):
        with pytest.raises(comms_listener.PushFormatError):
            await comms_listener.process_entries(redis, [(b"9-0", fields)])  # type: ignore[arg-type]
    assert redis.acked == []


@pytest.mark.asyncio
async def test_reconcile_keeps_the_cursor_after_each_page_and_starts_over_after_410(
    client: AsyncClient,
    db_session: AsyncSession,
    fake: FakeComms,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(comms_listener, "_PAGE_LIMIT", 2)
    s = await _setup(client, db_session, language="de")
    sent = await _person_writes(client, s, "Missed push")
    [row] = await _rows(db_session, sent["id"])
    await ship(db_session, fake)
    fake.answer(row.job_key, _answer("de", "Read by the feed"))
    fake.changes = ["other:1", "other:2", row.job_key]

    await comms_listener.reconcile()
    [row] = await _rows(db_session, sent["id"])
    assert row.outcome == "variant"
    assert await comms_listener.load_cursor() == "3"
    cursors = [c[3].get("cursor") for c in fake.calls if c[1].endswith("/changes")]
    assert cursors == [None, "2", "3"]  # the empty page ends the pass

    # 410: everything unfinished is re-read, the cursor starts over.
    fake.cursor_expired_once = True
    await comms_listener.reconcile()
    assert await comms_listener.load_cursor() == "3"


@pytest.mark.asyncio
async def test_a_page_of_another_shape_moves_no_cursor(fake: FakeComms) -> None:
    await comms_listener.save_cursor("7")

    async def odd(*args: Any, **kwargs: Any) -> Any:
        return {"items": [{"idempotency_key": "x"}]}  # no next_cursor

    original = comms_listener.comms_request
    comms_listener.comms_request = odd  # type: ignore[assignment]
    try:
        with pytest.raises(ValueError):
            await comms_listener.reconcile()
    finally:
        comms_listener.comms_request = original  # type: ignore[assignment]
    assert await comms_listener.load_cursor() == "7"


@pytest.mark.asyncio
async def test_one_active_listener() -> None:
    engine = get_engine()
    async with engine.connect() as first, engine.connect() as second:
        assert await comms_listener.try_lock(first) is True
        assert await comms_listener.try_lock(second) is False
        await comms_listener._release(first)
        assert await comms_listener.try_lock(second) is True
        await comms_listener._release(second)


def test_overlapping_prefixes_are_refused() -> None:
    noop = comms_listener.KeyHandler
    async def _n(*_: Any) -> None:
        return None
    with pytest.raises(ValueError):
        comms_listener.register(noop(prefix="aivis:llm-", on_key=_n, resume=_n, sweep=_n))
    # The same prefix again is a no-op, not a second handler.
    before = list(comms_listener._HANDLERS)
    comms_listener.register(
        noop(prefix=translation.JOB_PREFIX, on_key=_n, resume=_n, sweep=_n),
    )
    assert comms_listener._HANDLERS == before


def test_the_listener_starts_only_where_comms_is(monkeypatch: pytest.MonkeyPatch) -> None:
    for api, redis_url, expected in (
        ("", "", False), ("http://c", "", False), ("", "redis://r", False),
        ("http://c", "redis://r", True),
    ):
        monkeypatch.setattr(settings, "comms_api_url", api)
        monkeypatch.setattr(settings, "comms_redis_url", redis_url)
        assert comms_listener.configured() is expected


# ---------------------------------------------------------------------------
# 7. The letter leaves the outbox at publication
# ---------------------------------------------------------------------------


class _XaddRedis:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def xadd(self, stream: str, fields: dict) -> str:
        self.sent.append(fields)
        return "1-0"


@pytest.mark.asyncio
async def test_the_relay_drops_an_llm_letter_when_it_publishes_it(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(
        update(OutboxEvent)
        .where(OutboxEvent.published_at.is_(None))
        .values(published_at=datetime.now(UTC))
    )
    letter_event = await enqueue_llm_job(
        db_session,
        idempotency_key=f"aivis:llm-support-tr:{uuid4()}:en:1",
        type=translation.FOR_SUPPORT_TYPE,
        messages=[{"role": "user", "content": "SECRET WORDS"}],
    )
    plain = await emit_event(
        db_session,
        EVENT_NOTIFICATION_REQUEST,
        {"idempotency_key": f"t-{uuid4()}", "type": "kyc.approved",
         "target_type": "user", "target_value": str(uuid4()),
         "title": "kept", "body": "kept body"},
    )
    redis = _XaddRedis()
    published, failed = await relay_pending_batch(redis, session=db_session)  # type: ignore[arg-type]
    assert (published, failed) == (2, 0)
    # Shipped whole...
    assert "SECRET WORDS" in json.dumps([f["data"] for f in redis.sent], ensure_ascii=False)
    # ...and gone from the row, the envelope's key and type kept.
    assert letter_event.payload["llm"] == LLM_LETTER_REDACTED
    assert letter_event.payload["idempotency_key"].startswith("aivis:llm-support-tr:")
    assert "SECRET WORDS" not in json.dumps(letter_event.payload)
    assert plain.payload["body"] == "kept body"  # the pair: others untouched
    await db_session.rollback()


# ---------------------------------------------------------------------------
# 8. SUPPORT_LANGUAGE
# ---------------------------------------------------------------------------


def _settings(**over: Any) -> Settings:
    return Settings(_env_file=None, app_env="development", **over)  # type: ignore[call-arg]


@pytest.fixture
def no_support_language_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test about SUPPORT_LANGUAGE NOT BEING SET must not read the box's.

    The installer writes SUPPORT_LANGUAGE into backend/.env, and the suite
    runs inside the app container whose environment carries it; Settings
    reads the environment for every field the test does not pass. Without
    this, "not set" is whatever the box was installed with -- which is how
    both tests below first reached a box: green here, red there.
    """
    monkeypatch.delenv("SUPPORT_LANGUAGE", raising=False)


def test_support_language_defaults_in_development_and_is_normalized(
    no_support_language_env: None,
) -> None:
    assert _settings().support_language == "en"
    assert _settings(support_language=" RU ").support_language == "ru"


@pytest.mark.parametrize("value", ["de", "english", "en-US"])
def test_support_language_outside_the_interface_refuses_the_start(value: str) -> None:
    with pytest.raises(ValueError, match="SUPPORT_LANGUAGE"):
        _settings(support_language=value)


def test_support_language_is_required_outside_development(
    no_support_language_env: None,
) -> None:
    with pytest.raises(ValueError, match="SUPPORT_LANGUAGE"):
        Settings(_env_file=None, app_env="production")  # type: ignore[call-arg]
