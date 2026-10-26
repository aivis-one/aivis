# =============================================================================
# AIVIS.ONE Backend -- Tests: the transaction ends BEFORE the response (H46)
# =============================================================================
#
# THE HARNESS IS THE POINT. The suite's `client` fixture (httpx
# ASGITransport) builds its Response only after the ASGI app has returned,
# i.e. after every dependency teardown -- under it a commit that runs after
# the response is sent looks the same as one before it, and a failed commit
# arrives in the test as a raised exception rather than as the 200 a real
# client would have received. So these tests call the ASGI app directly and
# record each `send` message next to each commit and close: the order of
# `http.response.start` against them is the order on the wire (uvicorn writes
# to the socket on every send; measured for H44 under real uvicorn).
#
# TWO APPS. A small FastAPI app of its own with the REAL get_db_session,
# get_db_reader and get_current_user_write on the suite's database -- the
# property lives in the dependencies and FastAPI's teardown -- and the
# product's own app, for one real writing route (PATCH /api/v1/users/me):
# its middleware and global dependencies must not change the order.
# The mechanism follows VELO's BE-83 (tests/test_db_session_order.py there).
#
# Rows of the small app are audit_logs rows (no foreign key), marked by event
# and a per-test target_id, and deleted after each test.
#
# AXES: repeat -- two requests in a row, two sessions, two commits; emptiness
# -- a read-only session ends before the response too and writes nothing;
# shortage -- a refused commit reaches the client as a 500, never a 200, and
# an exception after a write rolls it back.
# =============================================================================

import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from httpx import AsyncClient
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.database import get_db_reader, get_db_session, get_session_factory
from app.main import app as product_app
from app.modules.auth.dependencies import get_current_user_write
from app.modules.users.models import User
from tests.helpers import register_user

EVENT = "h46_db_session_order"


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every AsyncSession.commit and .close next to the ASGI sends.

    A session whose info carries "fail_commit" raises instead of committing
    -- the stand-in for a commit the database refuses.
    """
    log: list[str] = []
    real_commit = AsyncSession.commit
    real_close = AsyncSession.close

    async def recording_commit(self: AsyncSession) -> None:
        log.append(f"commit:{id(self)}")
        if self.info.get("fail_commit"):
            raise RuntimeError("H46 test: the commit is refused")
        await real_commit(self)

    async def recording_close(self: AsyncSession) -> None:
        log.append(f"close:{id(self)}")
        await real_close(self)

    monkeypatch.setattr(AsyncSession, "commit", recording_commit)
    monkeypatch.setattr(AsyncSession, "close", recording_close)
    return log


@pytest.fixture
async def target() -> AsyncGenerator[UUID, None]:
    """A per-test target_id; this test's rows are removed afterwards."""
    target_id = uuid4()
    yield target_id
    async with get_session_factory()() as session:
        await session.execute(delete(AuditLog).where(AuditLog.target_id == target_id))
        await session.commit()


def _row(target_id: UUID, label: str) -> AuditLog:
    return AuditLog(
        event=EVENT, actor_type="system", target_type=label, target_id=target_id
    )


async def _labels(target_id: UUID) -> list[str]:
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(AuditLog.target_type).where(AuditLog.target_id == target_id)
        )
        return sorted(rows.scalars())


async def _nested(session: AsyncSession = Depends(get_db_session)) -> AsyncSession:
    """A sub-dependency on the session, the shape of get_current_user_write."""
    return session


def _app() -> FastAPI:
    app = FastAPI()
    # Every session /write receives, the OBJECT itself: holding it keeps it
    # alive for the whole test, so two of them can be told apart by identity
    # (an id() of a freed object may be reused).
    app.state.sessions = []

    @app.post("/write")
    async def write(
        request: Request, session: AsyncSession = Depends(get_db_session)
    ) -> dict[str, Any]:
        target_id = UUID(request.query_params["t"])
        session.add(_row(target_id, request.query_params.get("label", "write")))
        await session.flush()
        app.state.sessions.append(session)
        if request.query_params.get("fail") == "1":
            session.info["fail_commit"] = True
        if request.query_params.get("raise") == "1":
            raise HTTPException(status_code=409, detail="refused after the write")
        return {"ok": True}

    @app.get("/read")
    async def read(
        request: Request, session: AsyncSession = Depends(get_db_reader)
    ) -> dict[str, Any]:
        app.state.sessions.append(session)
        n = await session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.target_id == UUID(request.query_params["t"]))
        )
        return {"n": n}

    @app.post("/nested")
    async def nested(
        request: Request,
        session: AsyncSession = Depends(get_db_session),
        inner: AsyncSession = Depends(_nested),
    ) -> dict[str, Any]:
        session.add(_row(UUID(request.query_params["t"]), "two"))
        await session.flush()
        return {"same": session is inner}

    @app.post("/user")
    async def user_route(
        user: User = Depends(get_current_user_write),
        session: AsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        # inspect() gives the ORM Session under the AsyncSession.
        return {"same": inspect(user).session is session.sync_session}

    return app


async def _call(
    app: Any,
    events: list[str],
    method: str,
    path: str,
    query: str = "",
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
    on_start: Any = None,
) -> tuple[list[int], bytes]:
    """Run one request through the raw ASGI interface.

    Returns the status of every http.response.start (normally exactly one)
    and the body; appends "start:<status>" to `events` at the moment the
    start is sent, after running `on_start`. An exception the app re-raises
    after its error response (Starlette's ServerErrorMiddleware does that) is
    recorded, not propagated.
    """
    statuses: list[int] = []
    chunks: list[bytes] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            if on_start is not None:
                await on_start()
            statuses.append(message["status"])
            events.append(f"start:{message['status']}")
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [(b"host", b"test"), *(headers or [])],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "root_path": "",
    }
    try:
        await app(scope, receive, send)
    except Exception as exc:
        events.append(f"raised:{type(exc).__name__}")
    return statuses, b"".join(chunks)


def _of(events: list[str], kind: str, session: AsyncSession | None = None) -> list[str]:
    marks = [e for e in events if e.startswith(f"{kind}:")]
    if session is not None:
        marks = [e for e in marks if e == f"{kind}:{id(session)}"]
    return marks


# ---------------------------------------------------------------------------
# The write session
# ---------------------------------------------------------------------------


async def test_the_commit_runs_before_the_first_byte(
    events: list[str], target: UUID
) -> None:
    app = _app()
    statuses, _ = await _call(app, events, "POST", "/write", f"t={target}")

    assert statuses == [200]
    session = app.state.sessions[0]
    commit = _of(events, "commit", session)
    close = _of(events, "close", session)
    assert len(commit) == 1 and len(close) == 1
    assert events.index(commit[0]) < events.index(close[0]) < events.index("start:200")
    assert await _labels(target) == ["write"]


async def test_a_failed_commit_reaches_the_client_as_a_500_not_a_200(
    events: list[str], target: UUID
) -> None:
    app = _app()
    statuses, _ = await _call(app, events, "POST", "/write", f"t={target}&fail=1")

    assert statuses == [500]
    assert "start:200" not in events
    assert len(_of(events, "commit")) == 1
    assert events.index(_of(events, "commit")[0]) < events.index("start:500")
    assert await _labels(target) == []


async def test_an_exception_after_the_first_write_rolls_it_back(
    events: list[str], target: UUID
) -> None:
    app = _app()
    refused, _ = await _call(
        app, events, "POST", "/write", f"t={target}&label=refused&raise=1"
    )
    kept, _ = await _call(app, events, "POST", "/write", f"t={target}&label=kept")

    assert refused == [409]
    assert kept == [200]
    assert await _labels(target) == ["kept"]


async def test_two_requests_in_a_row_commit_independently(
    events: list[str], target: UUID
) -> None:
    app = _app()
    first, _ = await _call(app, events, "POST", "/write", f"t={target}&label=a")
    second, _ = await _call(app, events, "POST", "/write", f"t={target}&label=b")

    assert first == second == [200]
    sessions = app.state.sessions
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert len(_of(events, "commit")) == 2
    assert await _labels(target) == ["a", "b"]


async def test_every_declaration_in_a_request_shares_one_session(
    events: list[str], target: UUID
) -> None:
    statuses, body = await _call(_app(), events, "POST", "/nested", f"t={target}")
    assert statuses == [200]
    assert json.loads(body) == {"same": True}
    assert len(_of(events, "commit")) == 1
    assert await _labels(target) == ["two"]


async def test_get_current_user_write_holds_the_request_session(
    client: AsyncClient, events: list[str]
) -> None:
    body = await register_user(client)
    token = body["session_token"].encode()
    statuses, answer = await _call(
        _app(),
        events,
        "POST",
        "/user",
        headers=[(b"authorization", b"Bearer " + token)],
    )
    assert statuses == [200]
    assert json.loads(answer) == {"same": True}


# ---------------------------------------------------------------------------
# The read-only session
# ---------------------------------------------------------------------------


async def test_the_read_session_ends_before_the_first_byte_and_writes_nothing(
    events: list[str], target: UUID
) -> None:
    app = _app()
    await _call(app, events, "POST", "/write", f"t={target}&label=seed")
    events.clear()
    statuses, body = await _call(app, events, "GET", "/read", f"t={target}")

    assert statuses == [200]
    assert json.loads(body) == {"n": 1}
    reader = app.state.sessions[-1]
    close = _of(events, "close", reader)
    assert len(close) == 1
    assert events.index(close[0]) < events.index("start:200")
    assert _of(events, "commit") == []
    assert await _labels(target) == ["seed"]


# ---------------------------------------------------------------------------
# A real writing route of the product
# ---------------------------------------------------------------------------


async def test_a_product_route_commits_before_its_answer(
    client: AsyncClient, events: list[str]
) -> None:
    """PATCH /api/v1/users/me through the product's whole app (middleware,
    global dependencies): read from another session at http.response.start,
    the change is already there."""
    body = await register_user(client)
    user_id = UUID(body["user"]["id"])
    new_name = f"H46-{uuid4().hex[:8]}"
    seen: list[str | None] = []

    async def on_start() -> None:
        async with get_session_factory()() as session:
            profile = await session.scalar(
                select(User.profile).where(User.id == user_id)
            )
            seen.append((profile or {}).get("first_name"))

    payload = json.dumps({"profile": {"first_name": new_name}}).encode()
    statuses, _ = await _call(
        product_app,
        events,
        "PATCH",
        "/api/v1/users/me",
        headers=[
            (b"authorization", b"Bearer " + body["session_token"].encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode()),
        ],
        body=payload,
        on_start=on_start,
    )

    assert statuses == [200]
    assert seen == [new_name]
