# =============================================================================
# AIVIS.ONE Backend -- Support channel, user side (T-65)
# =============================================================================
#
# What is pinned here is mostly what must NOT happen. comms authenticates
# the PRODUCT and trusts every actor id it is handed, so the checks in
# this module are the only thing standing between one user and another
# user's conversation. Four properties carry that weight:
#
#   1. a thread that is not the caller's is a 404 -- and so is one that
#      does not exist, indistinguishably;
#   2. no actor name is readable from a request, on any of the three
#      surfaces a request has (body / query / path);
#   3. comms being down produces an answer, never a 500 and never a
#      silent success;
#   4. opening the channel twice is the same conversation and one row.
#
# comms is faked at the module boundary (app.core.comms.httpx), the same
# way test_comms_client.py fakes it and for the same reason: the outcomes
# under test include ones a live service cannot be asked for on demand.
# The fake answers the whole surface this module uses, so a call to a
# path nobody implemented shows up as a test failure rather than as a
# plausible default.
#
# REGISTER FIRST, ARM FAILURES SECOND. Registration itself calls comms
# (the recipient upsert), and a failed upsert commits an outbox row --
# which test_comms_relay.py would then find and fail on, an exact-count
# assertion. Every test here therefore registers its user while the fake
# is healthy and only then breaks it.
# =============================================================================

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import comms as comms_module
from app.core.config import settings
from app.modules.support import service as support_service
from app.modules.support.models import SupportThread
from tests.helpers import auth_headers, register_user

_URL = "http://comms.test"
_TOKEN = "t65-service-token"
_SECTION_ID = "11111111-1111-4111-8111-111111111111"

# Sentinel: a 200 whose body is not JSON at all.
_NOT_JSON = object()


# ---------------------------------------------------------------------------
# The fake comms
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = "" if payload is _NOT_JSON else str(payload)

    def json(self) -> Any:
        if self._payload is _NOT_JSON:
            raise ValueError("not json")
        return self._payload


class _FakeComms:
    """An in-memory comms with the create-or-get behaviour that matters.

    Dedup is keyed on (client, operator_value) exactly as comms dedups a
    subjectless dm, because "opening twice is the same thread" is the
    property the product leans on -- faking it as "always a new thread"
    would test a service this one is not.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.threads: dict[tuple[str, str], dict[str, Any]] = {}
        self.unread: dict[str, int] = {}
        # Armed by a test to break the next call. An exception instance
        # is raised from the wire; an int is answered as that status.
        self.fail_with: Any = None
        # Same, but for the thread-create call ONLY. Separate because a
        # status armed globally lands on the section resolve first, and
        # a test aimed at "comms refused to create the thread" would
        # then be measuring a different call than its name claims.
        self.create_fails_with: int | None = None
        # Overrides the create response, for the malformed-payload test.
        self.thread_payload: Any = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self

        class _FakeClient:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            async def __aenter__(self) -> "_FakeClient":
                return self

            async def __aexit__(self, *exc_info: Any) -> bool:
                return False

            async def request(
                self,
                method: str,
                url: str,
                params: dict | None = None,
                json: dict | None = None,
                headers: dict | None = None,
            ) -> _FakeResponse:
                return fake.handle(method, url, params, json, headers)

        monkeypatch.setattr(comms_module.httpx, "AsyncClient", _FakeClient)

    def handle(
        self,
        method: str,
        url: str,
        params: dict | None,
        json: dict | None,
        headers: dict | None,
    ) -> _FakeResponse:
        path = url[len(_URL) :]
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json": json,
                "headers": headers,
            }
        )

        # The recipient upsert (registration) is deliberately NOT broken
        # by fail_with: see the module header on outbox residue.
        if path.startswith("/api/v1/recipients/"):
            return _FakeResponse(200, {})

        if isinstance(self.fail_with, Exception):
            raise self.fail_with
        if isinstance(self.fail_with, int):
            return _FakeResponse(self.fail_with, {"detail": "comms said no"})

        if path == "/api/v1/sections":
            return _FakeResponse(
                200, {"id": _SECTION_ID, "key": "support", "label": "Support"}
            )

        if path == "/api/v1/threads":
            return self._create_thread(json or {})

        if path == "/api/v1/threads/unread-counts":
            wanted = (json or {}).get("thread_ids") or []
            counts = {
                tid: self.unread[tid] for tid in wanted if tid in self.unread
            }
            return _FakeResponse(200, {"counts": counts})

        if path.endswith("/messages") and method == "POST":
            return _FakeResponse(
                200,
                {
                    "id": str(uuid4()),
                    "thread_id": path.split("/")[4],
                    "sender": (json or {}).get("sender"),
                    "body": (json or {}).get("body"),
                },
            )

        if path.endswith("/messages") and method == "GET":
            return _FakeResponse(200, {"messages": [], "next_cursor": None})

        if path.endswith("/read"):
            return _FakeResponse(200, {"unread": 0})

        raise AssertionError(f"fake comms has no route for {method} {path}")

    def _create_thread(self, body: dict[str, Any]) -> _FakeResponse:
        if self.create_fails_with is not None:
            return _FakeResponse(
                self.create_fails_with,
                {"detail": f"client recipient {body.get('client')} "
                           "does not exist"},
            )
        if self.thread_payload is not None:
            return _FakeResponse(200, self.thread_payload)
        key = (str(body.get("client")), str(body.get("operator_value")))
        existing = self.threads.get(key)
        if existing is not None:
            return _FakeResponse(200, {**existing, "created": False})
        thread = {
            "id": str(uuid4()),
            "client": body.get("client"),
            "operator_kind": body.get("operator_kind"),
            "operator_value": body.get("operator_value"),
            "kind": body.get("kind"),
            "status": "open",
            "assignee": None,
        }
        self.threads[key] = thread
        return _FakeResponse(200, {**thread, "created": True})

    def bodies(self, path_suffix: str) -> list[dict[str, Any]]:
        """Bodies of the calls whose path ends with `path_suffix`."""
        return [
            call["json"]
            for call in self.calls
            if call["path"].endswith(path_suffix) and call["json"] is not None
        ]


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> _FakeComms:
    """A configured comms address plus the fake behind it.

    The section id cache is cleared per test: it is process-global, and a
    value cached by a neighbour would hide a failed resolve here.
    """
    monkeypatch.setattr(settings, "comms_api_url", _URL)
    monkeypatch.setattr(settings, "comms_service_token", _TOKEN)
    monkeypatch.setattr(support_service, "_support_section_id", None)
    fake = _FakeComms()
    fake.install(monkeypatch)
    return fake


async def _registered(client: AsyncClient) -> tuple[dict[str, str], UUID]:
    """A registered user: auth headers and their id."""
    body = await register_user(client)
    return auth_headers(body["session_token"]), UUID(body["user"]["id"])


async def _pointer_count(session: AsyncSession, user_id: UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(SupportThread)
        .where(SupportThread.user_id == user_id)
    )
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# 1. Trust model: no actor name is readable from a request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_actor_fields_in_a_body_are_refused(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """Every model forbids extra fields, so an actor sent in a body is a
    422 rather than a field quietly ignored. Ignoring would be safe and
    mute; this leaves a trace."""
    headers, _ = await _registered(client)

    opened = await client.post("/api/v1/support/threads", headers=headers)
    assert opened.status_code == 200, opened.text
    thread_id = opened.json()["id"]

    for path, payload in (
        ("/api/v1/support/threads", {"client": str(uuid4())}),
        (
            "/api/v1/support/threads/messages",
            {"body": "hi", "sender": str(uuid4())},
        ),
        (
            f"/api/v1/support/threads/{thread_id}/read",
            {"participant": str(uuid4())},
        ),
    ):
        response = await client.post(path, json=payload, headers=headers)
        assert response.status_code == 422, f"{path}: {response.text}"


@pytest.mark.asyncio
async def test_the_session_is_what_reaches_comms(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """The positive twin of the refusals above: with no actor on the
    wire, the ids comms receives are the session's -- and they are the
    ONLY ones it could have received."""
    headers, user_id = await _registered(client)

    opened = await client.post("/api/v1/support/threads", headers=headers)
    thread_id = opened.json()["id"]
    await client.post(
        "/api/v1/support/threads/messages",
        json={"body": "my card was declined"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/support/threads/{thread_id}/read", headers=headers
    )

    assert comms.bodies("/api/v1/threads")[0]["client"] == str(user_id)
    assert comms.bodies("/messages")[0]["sender"] == str(user_id)
    read_body = comms.bodies("/read")[0]
    assert read_body["participant"] == str(user_id)
    # last_read_at is not accepted from the wire and not sent: comms
    # stamps now.
    assert "last_read_at" not in read_body


@pytest.mark.asyncio
async def test_actor_params_in_a_query_are_refused(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """Same guarantee on the query surface, by a different mechanism: a
    400 that names the offender, on every route."""
    headers, _ = await _registered(client)
    opened = await client.post("/api/v1/support/threads", headers=headers)
    thread_id = opened.json()["id"]

    base = "/api/v1/support/threads"
    for method, path in (
        ("POST", base),
        ("GET", base),
        ("POST", f"{base}/messages"),
        ("GET", f"{base}/{thread_id}/messages"),
        ("POST", f"{base}/{thread_id}/read"),
    ):
        for query in (
            "participant=" + str(uuid4()),
            "operator=" + str(uuid4()),
            "is_supervisor=true",
        ):
            response = await client.request(
                method,
                f"{path}?{query}",
                headers=headers,
                json={"body": "hi"} if path.endswith("/messages") else None,
            )
            assert response.status_code == 400, (
                f"{method} {path}?{query}: {response.text}"
            )
            assert query.split("=")[0] in response.json()["message"]


# ---------------------------------------------------------------------------
# 2. Ownership: a thread that is not yours does not exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_foreign_thread_is_not_readable(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """The whole point of the local pointer. comms would have answered
    both of these happily -- its feed endpoint has no gate of its own."""
    owner_headers, _ = await _registered(client)
    opened = await client.post(
        "/api/v1/support/threads", headers=owner_headers
    )
    thread_id = opened.json()["id"]

    stranger_headers, _ = await _registered(client)
    feed = await client.get(
        f"/api/v1/support/threads/{thread_id}/messages",
        headers=stranger_headers,
    )
    read = await client.post(
        f"/api/v1/support/threads/{thread_id}/read",
        headers=stranger_headers,
    )
    assert feed.status_code == 404, feed.text
    assert read.status_code == 404, read.text

    # The twin: the owner still gets in. A check that only proved the
    # door was shut would pass just as well if it were welded.
    own_feed = await client.get(
        f"/api/v1/support/threads/{thread_id}/messages",
        headers=owner_headers,
    )
    assert own_feed.status_code == 200, own_feed.text


@pytest.mark.asyncio
async def test_an_unknown_thread_looks_exactly_like_a_foreign_one(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """Existence must not leak: a real thread belonging to someone else
    and an id that names nothing answer identically."""
    owner_headers, _ = await _registered(client)
    opened = await client.post(
        "/api/v1/support/threads", headers=owner_headers
    )
    real_but_foreign = opened.json()["id"]

    stranger_headers, _ = await _registered(client)
    foreign = await client.get(
        f"/api/v1/support/threads/{real_but_foreign}/messages",
        headers=stranger_headers,
    )
    nowhere = await client.get(
        f"/api/v1/support/threads/{uuid4()}/messages",
        headers=stranger_headers,
    )

    assert foreign.status_code == nowhere.status_code == 404
    assert foreign.json() == nowhere.json()


@pytest.mark.asyncio
async def test_support_requires_a_session(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """No route here is reachable without authentication."""
    response = await client.get("/api/v1/support/threads")
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# 3. Repetition: one conversation, one row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reopening_returns_the_same_thread_and_one_row(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Opening the channel is idempotent -- the client calls it before
    every send, so a second call must not mean a second conversation."""
    headers, user_id = await _registered(client)

    first = await client.post("/api/v1/support/threads", headers=headers)
    second = await client.post("/api/v1/support/threads", headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert await _pointer_count(db_session, user_id) == 1
    # The seam flag is comms' business, not the caller's.
    assert "created" not in second.json()


@pytest.mark.asyncio
async def test_the_thread_is_a_pooled_conversation_not_a_ticket(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """The shape decision, pinned where it can be read: a section
    operator (so the request lands in a pool) and a dm kind (so it is one
    eternal conversation). A subjectless ticket would dedup to nothing
    and multiply rows on every press."""
    headers, _ = await _registered(client)
    await client.post("/api/v1/support/threads", headers=headers)

    body = comms.bodies("/api/v1/threads")[0]
    assert body["operator_kind"] == "section"
    assert body["kind"] == "dm"
    assert body["operator_value"] == _SECTION_ID
    assert "subject_type" not in body and "subject_id" not in body


# ---------------------------------------------------------------------------
# 4. Emptiness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_user_with_no_request_gets_an_empty_list(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """Nothing to show is a list of nothing, not a 404."""
    headers, _ = await _registered(client)

    response = await client.get("/api/v1/support/threads", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"threads": []}


@pytest.mark.asyncio
async def test_an_empty_or_missing_message_is_refused(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """A message with no text is not a message."""
    headers, _ = await _registered(client)
    await client.post("/api/v1/support/threads", headers=headers)

    empty = await client.post(
        "/api/v1/support/threads/messages",
        json={"body": ""},
        headers=headers,
    )
    missing = await client.post(
        "/api/v1/support/threads/messages", json={}, headers=headers
    )

    assert empty.status_code == 422, empty.text
    assert missing.status_code == 422, missing.text


@pytest.mark.asyncio
async def test_opening_needs_no_body_at_all(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """Everything the verb needs is in the session, so an absent body is
    the normal case rather than a missing argument."""
    headers, _ = await _registered(client)

    response = await client.post("/api/v1/support/threads", headers=headers)

    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# 5. Shortage: comms is not there, or answers something unusable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comms_down_on_open_refuses_and_writes_no_pointer(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """A refusal the user can act on -- and no pointer, because a row
    aimed at a thread that may not exist answers every later ownership
    question wrongly.

    The second half is the twin: the same process opens the channel
    successfully once comms is back, which also proves the failed
    section resolve did not poison the in-process cache.
    """
    headers, user_id = await _registered(client)
    comms.fail_with = httpx.ConnectError("comms is down")

    refused = await client.post("/api/v1/support/threads", headers=headers)

    assert refused.status_code == 502, refused.text
    assert refused.json()["error"] == "comms_unavailable"
    assert await _pointer_count(db_session, user_id) == 0

    comms.fail_with = None
    recovered = await client.post("/api/v1/support/threads", headers=headers)
    assert recovered.status_code == 200, recovered.text
    assert await _pointer_count(db_session, user_id) == 1


@pytest.mark.asyncio
async def test_comms_timeout_on_send_is_answered_not_crashed(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """504, not a 500: the person pressed send and is owed the outcome.
    A 500 would say nothing and look like our bug to them."""
    headers, _ = await _registered(client)
    await client.post("/api/v1/support/threads", headers=headers)
    comms.fail_with = httpx.ReadTimeout("timed out")

    response = await client.post(
        "/api/v1/support/threads/messages",
        json={"body": "still there?"},
        headers=headers,
    )

    assert response.status_code == 504, response.text
    assert response.json()["error"] == "comms_timeout"


@pytest.mark.asyncio
async def test_sending_before_opening_is_a_404(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """There is no thread to resolve, and auto-opening here would make a
    failed open indistinguishable from a failed send."""
    headers, _ = await _registered(client)

    response = await client.post(
        "/api/v1/support/threads/messages",
        json={"body": "hello?"},
        headers=headers,
    )

    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_a_malformed_comms_answer_is_a_refusal_not_a_crash(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """comms' answer is input too. A 200 with no thread id must not
    become a KeyError on a request somebody is watching."""
    headers, user_id = await _registered(client)
    comms.thread_payload = {"status": "open"}  # no "id"

    response = await client.post("/api/v1/support/threads", headers=headers)

    assert response.status_code == 502, response.text
    assert await _pointer_count(db_session, user_id) == 0


@pytest.mark.asyncio
async def test_an_unsynced_recipient_is_reported_as_not_ready(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """comms delivers to known recipients only, and the sync can lag.
    That is transient and not the user's doing, so it is reported as
    "not ready" -- and comms' own wording about missing rows stays
    inside."""
    headers, _ = await _registered(client)
    comms.create_fails_with = 404

    response = await client.post("/api/v1/support/threads", headers=headers)

    assert response.status_code == 502, response.text
    assert response.json()["error"] == "comms_recipient_pending"
    # comms' own words ("client recipient <uuid> does not exist") name an
    # internal row and must not reach a product response.
    assert "recipient" not in response.json()["message"].lower()


# ---------------------------------------------------------------------------
# 6. The list degrades without lying
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unread_is_reported_when_comms_answers(
    client: AsyncClient, comms: _FakeComms
) -> None:
    headers, _ = await _registered(client)
    opened = await client.post("/api/v1/support/threads", headers=headers)
    comms.unread[opened.json()["id"]] = 3

    response = await client.get("/api/v1/support/threads", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["threads"][0]["unread"] == 3


@pytest.mark.asyncio
async def test_unread_is_absent_never_zero_when_it_is_unknown(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """Two ways the count can be unknown -- comms down, and a thread it
    does not count for the caller -- and both answer the same way: no
    key. A zero would read as "nothing unread here" and be
    indistinguishable from a fully read conversation.

    The list itself still answers: those rows are ours, and refusing a
    read the product can serve would be a worse trade than an absent
    enrichment.
    """
    headers, _ = await _registered(client)
    await client.post("/api/v1/support/threads", headers=headers)

    # a) comms does not count this thread for the caller
    not_counted = await client.get(
        "/api/v1/support/threads", headers=headers
    )
    assert not_counted.status_code == 200, not_counted.text
    assert "unread" not in not_counted.json()["threads"][0]

    # b) comms is unreachable
    comms.fail_with = httpx.ConnectError("comms is down")
    degraded = await client.get("/api/v1/support/threads", headers=headers)

    assert degraded.status_code == 200, degraded.text
    rows = degraded.json()["threads"]
    assert len(rows) == 1
    assert "unread" not in rows[0]
