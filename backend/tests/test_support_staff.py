# =============================================================================
# AIVIS.ONE Backend -- Support channel, operator side (T-66)
# =============================================================================
#
# The stake here is wider than on the user side. comms does not verify
# `operator` and cannot verify `is_supervisor` -- it has no role registry
# -- and a true `is_supervisor` makes it skip its scope filter and return
# EVERY thread of EVERY user. So the properties pinned here are:
#
#   1. only an active staff member with a profile gets through at all;
#   2. `operator` and `is_supervisor` reaching comms are what the session
#      and the staff profile say, and nothing a request can carry;
#   3. claiming is idempotent for its owner and a conflict for anyone
#      else, and a claimed thread leaves everybody else's pool;
#   4. replying without claiming is refused in a way that says what to do
#      -- not as "service unavailable";
#   5. status moves forward only, and comms being down is an answer.
#
# THE FAKE MODELS THE OPERATOR SURFACE, and it is a second fake rather
# than an import from test_support_threads.py on purpose: that one models
# the CLIENT surface (create-or-get dedup, unread batches), this one
# models visibility, the claim race guard and the D5 status matrix.
# Sharing one fake would mean a change made for one side could quietly
# weaken the other side's suite -- the sameness would be in the code, not
# in what is being asserted.
#
# The rules the fake reproduces are read from comms' bodies, not guessed:
#   visible(me)        = assignee == me OR (section AND unassigned)
#                        -- messaging/operators.list_visible_threads
#   claim              = UPDATE ... WHERE assignee IS NULL, rowcount
#                        decides `claimed` -- operators.claim_thread
#   can_post_message   = client or assignee, no supervisor bypass
#   status matrix      = open -> resolved|closed, resolved -> closed,
#                        X -> X no-op, everything else 422 -- status.py
#
# REGISTER FIRST, ARM FAILURES SECOND -- same reason as the user-side
# suite: registration calls comms, and a failed call commits an outbox
# row that test_comms_relay.py would find.
# =============================================================================

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import comms as comms_module
from app.core.config import settings
from app.modules.support import service as support_service
from app.modules.support.models import SupportThread
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    register_user,
)

_URL = "http://comms.test"
_TOKEN = "t66-service-token"
_SECTION_ID = "22222222-2222-4222-8222-222222222222"

_STAFF_BASE = "/api/v1/staff/support/threads"

# The manual transitions comms permits, copied from status.py so a
# divergence shows up here rather than in production.
_ALLOWED: dict[str, set[str]] = {
    "open": {"resolved", "closed"},
    "resolved": {"closed"},
    "closed": set(),
}


# ---------------------------------------------------------------------------
# The fake comms
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


class _FakeComms:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.threads: dict[str, dict[str, Any]] = {}
        self.unread: dict[str, int] = {}
        self.fail_with: Any = None

    # -- wiring ---------------------------------------------------------
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
                return fake.handle(method, url, params, json)

        monkeypatch.setattr(comms_module.httpx, "AsyncClient", _FakeClient)

    # -- state ----------------------------------------------------------
    def add_thread(
        self,
        *,
        client_id: UUID,
        assignee: UUID | None = None,
        status: str = "open",
    ) -> str:
        thread_id = str(uuid4())
        self.threads[thread_id] = {
            "id": thread_id,
            "client": str(client_id),
            "operator_kind": "section",
            "operator_value": _SECTION_ID,
            "kind": "dm",
            "status": status,
            "assignee": str(assignee) if assignee else None,
        }
        return thread_id

    # -- routing --------------------------------------------------------
    def handle(
        self,
        method: str,
        url: str,
        params: dict | None,
        json: dict | None,
    ) -> _FakeResponse:
        path = url[len(_URL) :]
        self.calls.append(
            {"method": method, "path": path, "params": params, "json": json}
        )

        if path.startswith("/api/v1/recipients/"):
            return _FakeResponse(200, {})

        if isinstance(self.fail_with, Exception):
            raise self.fail_with

        if path == "/api/v1/sections":
            return _FakeResponse(200, {"id": _SECTION_ID})

        if path == "/api/v1/threads" and method == "GET":
            return self._list(params or {})

        parts = path.strip("/").split("/")
        # /api/v1/threads/{id}/{verb}
        if len(parts) == 5 and parts[2] == "threads":
            thread = self.threads.get(parts[3])
            if thread is None:
                return _FakeResponse(404, {"detail": "thread does not exist"})
            if parts[4] == "claim":
                return self._claim(thread, json or {})
            if parts[4] == "messages":
                return self._post_message(thread, json or {})
            if parts[4] == "status":
                return self._status(thread, json or {})

        raise AssertionError(f"fake comms has no route for {method} {path}")

    def _list(self, params: dict[str, Any]) -> _FakeResponse:
        operator = str(params.get("operator"))
        supervisor = bool(params.get("is_supervisor"))
        rows = []
        for thread in self.threads.values():
            visible = supervisor or (
                thread["assignee"] == operator
                or (
                    thread["operator_kind"] == "section"
                    and thread["assignee"] is None
                )
            )
            if not visible:
                continue
            row = dict(thread)
            # The unread key rides only on threads the operator TAKES
            # PART IN. An unclaimed pool thread belongs to nobody, so it
            # never gets one -- absence, never a zero.
            if params.get("with_unread") and thread["assignee"] == operator:
                row["unread"] = self.unread.get(thread["id"], 0)
            rows.append(row)
        return _FakeResponse(200, {"threads": rows, "next_cursor": None})

    def _claim(
        self, thread: dict[str, Any], body: dict[str, Any]
    ) -> _FakeResponse:
        if thread["assignee"] is None:
            thread["assignee"] = str(body.get("operator"))
            return _FakeResponse(200, {"claimed": True, "thread": dict(thread)})
        return _FakeResponse(200, {"claimed": False, "thread": dict(thread)})

    def _post_message(
        self, thread: dict[str, Any], body: dict[str, Any]
    ) -> _FakeResponse:
        sender = str(body.get("sender"))
        if sender not in (thread["client"], thread["assignee"]):
            return _FakeResponse(
                403,
                {
                    "detail": "sender is neither a participant nor the "
                    "serving operator of this thread"
                },
            )
        return _FakeResponse(
            200,
            {
                "id": str(uuid4()),
                "thread_id": thread["id"],
                "sender": sender,
                "body": body.get("body"),
            },
        )

    def _status(
        self, thread: dict[str, Any], body: dict[str, Any]
    ) -> _FakeResponse:
        target = str(body.get("status"))
        current = thread["status"]
        if target == current:
            return _FakeResponse(200, dict(thread))
        if target not in _ALLOWED[current]:
            return _FakeResponse(
                422,
                {"detail": f"invalid status transition {current} -> {target}"},
            )
        thread["status"] = target
        return _FakeResponse(200, dict(thread))

    # -- reading the log ------------------------------------------------
    def params_of(self, path: str) -> list[dict[str, Any]]:
        return [
            call["params"]
            for call in self.calls
            if call["path"] == path and call["params"] is not None
        ]

    def bodies_of(self, suffix: str) -> list[dict[str, Any]]:
        return [
            call["json"]
            for call in self.calls
            if call["path"].endswith(suffix) and call["json"] is not None
        ]


@pytest.fixture
def comms(monkeypatch: pytest.MonkeyPatch) -> _FakeComms:
    monkeypatch.setattr(settings, "comms_api_url", _URL)
    monkeypatch.setattr(settings, "comms_service_token", _TOKEN)
    monkeypatch.setattr(support_service, "_support_section_id", None)
    fake = _FakeComms()
    fake.install(monkeypatch)
    return fake


# ---------------------------------------------------------------------------
# Fixtures for people and threads
# ---------------------------------------------------------------------------


async def _a_client_user(client: AsyncClient) -> UUID:
    """A registered ordinary user -- the person who asks for support."""
    body = await register_user(client)
    return UUID(body["user"]["id"])


async def _a_request(
    client: AsyncClient,
    session: AsyncSession,
    comms: _FakeComms,
    *,
    assignee: UUID | None = None,
    status: str = "open",
) -> str:
    """A support conversation that exists on BOTH sides.

    A FRESH client user every time, because support_threads holds one row
    per user (uq_support_threads_user) -- the product's own rule that a
    person has one eternal conversation, not a pile of tickets. A fixture
    that gave one user three threads would be building a state this
    database refuses, which is exactly what the first run of this suite
    found.

    The pointer row is written directly rather than through the user-side
    endpoint: what is under test is the operator side, and driving the
    other half of the product to set up a fixture would make these tests
    fail for reasons that have nothing to do with them.
    """
    client_id = await _a_client_user(client)
    thread_id = comms.add_thread(
        client_id=client_id, assignee=assignee, status=status
    )
    session.add(
        SupportThread(user_id=client_id, comms_thread_id=UUID(thread_id))
    )
    await session.commit()
    return thread_id


# ---------------------------------------------------------------------------
# 1. Who is let in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_ordinary_user_is_not_an_operator(
    client: AsyncClient, comms: _FakeComms
) -> None:
    """A support queue is not a place an investor can look into."""
    body = await register_user(client)

    response = await client.get(
        _STAFF_BASE, headers=auth_headers(body["session_token"])
    )

    assert response.status_code == 403, response.text
    assert comms.calls == [] or all(
        call["path"].startswith("/api/v1/recipients/")
        for call in comms.calls
    ), "a refused caller must not reach comms at all"


@pytest.mark.asyncio
async def test_a_deactivated_staff_profile_is_refused(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Deactivation has to mean something the same day it happens."""
    from sqlalchemy import select

    from app.modules.staff.models import StaffProfile

    user, token = await create_staff_user(client, db_session)
    profile = (
        await db_session.execute(
            select(StaffProfile).where(StaffProfile.user_id == user.id)
        )
    ).scalar_one()
    profile.is_active = False
    await db_session.commit()

    response = await client.get(_STAFF_BASE, headers=auth_headers(token))

    assert response.status_code == 403, response.text

    # Restored so the shared run is not left with a broken staff member.
    profile.is_active = True
    await db_session.commit()


@pytest.mark.asyncio
async def test_the_queue_needs_a_session(
    client: AsyncClient, comms: _FakeComms
) -> None:
    response = await client.get(_STAFF_BASE)
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# 2. The stamp: what actually reaches comms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_plain_operator_is_stamped_without_supervision(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """The positive half of the guarantee: not merely "no override
    accepted", but the values comms received are the session's and the
    profile's."""
    user, token = await create_staff_user(client, db_session)

    response = await client.get(_STAFF_BASE, headers=auth_headers(token))

    assert response.status_code == 200, response.text
    params = comms.params_of("/api/v1/threads")[0]
    assert params["operator"] == str(user.id)
    assert params["is_supervisor"] is False


@pytest.mark.asyncio
async def test_an_admin_is_stamped_as_supervisor(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Supervision is the product's existing admin mark -- every
    permission true -- resolved from the profile, never from a request."""
    user, token = await create_admin_user(client, db_session)

    response = await client.get(_STAFF_BASE, headers=auth_headers(token))

    assert response.status_code == 200, response.text
    params = comms.params_of("/api/v1/threads")[0]
    assert params["operator"] == str(user.id)
    assert params["is_supervisor"] is True


@pytest.mark.asyncio
async def test_supervision_cannot_be_forced_from_a_query(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """The one that matters most: a true is_supervisor makes comms skip
    its scope filter entirely."""
    _user, token = await create_staff_user(client, db_session)

    for query in ("is_supervisor=true", "operator=" + str(uuid4())):
        response = await client.get(
            f"{_STAFF_BASE}?{query}", headers=auth_headers(token)
        )
        assert response.status_code == 400, f"{query}: {response.text}"
        assert query.split("=")[0] in response.json()["message"]


@pytest.mark.asyncio
async def test_actor_fields_in_an_operator_body_are_refused(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    _user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms)

    for path, payload in (
        (f"{_STAFF_BASE}/{thread_id}/claim", {"operator": str(uuid4())}),
        (
            f"{_STAFF_BASE}/{thread_id}/messages",
            {"body": "hi", "sender": str(uuid4())},
        ),
        (
            f"{_STAFF_BASE}/{thread_id}/status",
            {"status": "closed", "is_supervisor": True},
        ),
    ):
        response = await client.post(
            path, json=payload, headers=auth_headers(token)
        )
        assert response.status_code == 422, f"{path}: {response.text}"


# ---------------------------------------------------------------------------
# 3. What each operator sees
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_plain_operator_sees_the_pool_and_their_own(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """comms' visibility rule, seen through the proxy: the unclaimed pool
    plus what this operator claimed -- and nothing a colleague holds."""
    mine, token = await create_staff_user(client, db_session)
    colleague, _ = await create_staff_user(client, db_session)

    unclaimed = await _a_request(client, db_session, comms)
    ours = await _a_request(client, db_session, comms, assignee=mine.id)
    theirs = await _a_request(client, db_session, comms, assignee=colleague.id)

    response = await client.get(_STAFF_BASE, headers=auth_headers(token))

    seen = {row["id"] for row in response.json()["threads"]}
    assert unclaimed in seen
    assert ours in seen
    assert theirs not in seen


@pytest.mark.asyncio
async def test_a_supervisor_sees_every_thread(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    _admin, token = await create_admin_user(client, db_session)
    colleague, _ = await create_staff_user(client, db_session)
    theirs = await _a_request(client, db_session, comms, assignee=colleague.id)

    response = await client.get(_STAFF_BASE, headers=auth_headers(token))

    assert theirs in {row["id"] for row in response.json()["threads"]}


@pytest.mark.asyncio
async def test_a_pool_row_carries_no_unread_count(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Named cost of asking for counts at all: nobody takes part in an
    unclaimed thread, so it never gets a number -- and an absent key must
    not become a zero on the way through."""
    mine, token = await create_staff_user(client, db_session)
    unclaimed = await _a_request(client, db_session, comms)
    ours = await _a_request(client, db_session, comms, assignee=mine.id)
    comms.unread[ours] = 2

    response = await client.get(_STAFF_BASE, headers=auth_headers(token))

    rows = {row["id"]: row for row in response.json()["threads"]}
    assert "unread" not in rows[unclaimed]
    assert rows[ours]["unread"] == 2


# ---------------------------------------------------------------------------
# 4. Claiming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claiming_an_unclaimed_request_takes_it(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/claim", headers=auth_headers(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["assignee"] == str(user.id)
    assert comms.bodies_of("/claim")[0] == {"operator": str(user.id)}


@pytest.mark.asyncio
async def test_claiming_your_own_request_again_changes_nothing(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Idempotence, not failure: the button may be pressed twice."""
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms, assignee=user.id)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/claim", headers=auth_headers(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["assignee"] == str(user.id)
    assert comms.threads[thread_id]["assignee"] == str(user.id)


@pytest.mark.asyncio
async def test_claiming_what_a_colleague_took_is_a_conflict(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """409 with a reason -- not a 500, and not a success that quietly
    left the thread with its original owner."""
    _mine, token = await create_staff_user(client, db_session)
    colleague, _ = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms, assignee=colleague.id)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/claim", headers=auth_headers(token)
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "support_thread_already_claimed"
    assert comms.threads[thread_id]["assignee"] == str(colleague.id)


@pytest.mark.asyncio
async def test_a_claimed_request_leaves_everybody_elses_pool(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """The consequence the queue depends on: two operators do not answer
    the same person because both still see the request."""
    _mine, mine_token = await create_staff_user(client, db_session)
    _other, other_token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms)

    before = await client.get(
        _STAFF_BASE, headers=auth_headers(other_token)
    )
    assert thread_id in {r["id"] for r in before.json()["threads"]}

    await client.post(
        f"{_STAFF_BASE}/{thread_id}/claim", headers=auth_headers(mine_token)
    )

    after = await client.get(_STAFF_BASE, headers=auth_headers(other_token))
    assert thread_id not in {r["id"] for r in after.json()["threads"]}


@pytest.mark.asyncio
async def test_an_unknown_thread_id_never_reaches_comms(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """The local pointer is the boundary: a guessed id is refused here,
    before the service is asked anything about it."""
    _user, token = await create_staff_user(client, db_session)
    stranger_id = uuid4()

    response = await client.post(
        f"{_STAFF_BASE}/{stranger_id}/claim", headers=auth_headers(token)
    )

    assert response.status_code == 404, response.text
    assert not any(str(stranger_id) in call["path"] for call in comms.calls)


# ---------------------------------------------------------------------------
# 5. Replying
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reply_goes_out_as_the_session_operator(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms, assignee=user.id)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/messages",
        json={"body": "Looking into it now"},
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert comms.bodies_of("/messages")[0]["sender"] == str(user.id)


@pytest.mark.asyncio
async def test_replying_without_claiming_says_what_to_do(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """comms refuses the write (client or assignee only). That refusal
    must arrive as "claim it first", not as "service unavailable" -- the
    two call for opposite reactions from whoever is looking at it."""
    _user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/messages",
        json={"body": "let me help"},
        headers=auth_headers(token),
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"] == "support_thread_not_claimed"


@pytest.mark.asyncio
async def test_a_supervisor_still_has_to_claim_before_replying(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Reading everything is not writing everything: comms has no
    supervisor bypass on can_post_message, and neither do we."""
    _admin, token = await create_admin_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/messages",
        json={"body": "stepping in"},
        headers=auth_headers(token),
    )

    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_an_empty_reply_is_refused(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms, assignee=user.id)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/messages",
        json={"body": ""},
        headers=auth_headers(token),
    )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 6. Status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_closing_moves_the_thread_and_repeating_it_is_a_no_op(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms, assignee=user.id)

    first = await client.post(
        f"{_STAFF_BASE}/{thread_id}/status",
        json={"status": "closed"},
        headers=auth_headers(token),
    )
    again = await client.post(
        f"{_STAFF_BASE}/{thread_id}/status",
        json={"status": "closed"},
        headers=auth_headers(token),
    )

    assert first.status_code == 200, first.text
    assert again.status_code == 200, again.text
    assert comms.threads[thread_id]["status"] == "closed"
    assert comms.bodies_of("/status")[0]["operator"] == str(user.id)


@pytest.mark.asyncio
async def test_a_backward_transition_is_refused_by_the_matrix(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """closed -> resolved does not exist. Nor does any manual reopen: a
    thread comes back only when the client writes into it."""
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(
        client, db_session, comms, assignee=user.id, status="closed"
    )

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/status",
        json={"status": "resolved"},
        headers=auth_headers(token),
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_reopening_is_not_even_offered(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Refused by our own schema, before comms is asked: an endpoint that
    accepted `open` would be advertising a transition that never
    succeeds."""
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(
        client, db_session, comms, assignee=user.id, status="closed"
    )
    before = len(comms.calls)

    response = await client.post(
        f"{_STAFF_BASE}/{thread_id}/status",
        json={"status": "open"},
        headers=auth_headers(token),
    )

    assert response.status_code == 422, response.text
    assert len(comms.calls) == before, "the schema refuses it locally"


@pytest.mark.asyncio
async def test_comms_being_down_is_an_answer_not_a_crash(
    client: AsyncClient, db_session: AsyncSession, comms: _FakeComms
) -> None:
    """Every operator verb degrades the same way: a status the caller can
    act on, never a 500."""
    user, token = await create_staff_user(client, db_session)
    thread_id = await _a_request(client, db_session, comms, assignee=user.id)
    comms.fail_with = httpx.ConnectError("comms is down")

    closing = await client.post(
        f"{_STAFF_BASE}/{thread_id}/status",
        json={"status": "closed"},
        headers=auth_headers(token),
    )
    listing = await client.get(_STAFF_BASE, headers=auth_headers(token))

    assert closing.status_code == 502, closing.text
    assert listing.status_code == 502, listing.text
    assert comms.threads[thread_id]["status"] == "open"
