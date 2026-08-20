# =============================================================================
# AIVIS.ONE Backend -- Comms client / recipient upsert tests (T-64)
# =============================================================================
#
# comms delivers to KNOWN recipients only, so this product creates the
# recipient synchronously when it creates the user. What is pinned here
# is mostly what must NOT happen: no call when comms is not configured,
# and no exception -- ever -- reaching the code that created the user.
#
# Covers:
#   1:  the snapshot is complete for every shape of user we create
#   2:  an empty COMMS_API_URL means no HTTP call at all
#   3:  success -> no outbox row (the fast path was enough)
#   4:  every failure (refused, timed out, 401, 500) -> False, never a
#       raise, and the recipient is deferred to the outbox instead
#   5:  registration still succeeds end-to-end while comms is down
#
# NOTHING IS COMMITTED except in test 5, which drives the real HTTP
# registration and therefore cannot avoid it -- that test cleans its own
# outbox row up afterwards. The reason is a sibling suite:
# test_comms_relay.py asserts an EMPTY outbox on an exact count, and a
# committed pending row left behind here would fail it.
#
# httpx is faked at the module boundary (app.core.comms.httpx) rather
# than by talking to a real server: what is under test is the client's
# behavior per outcome, and the outcomes include ones a live server
# cannot be asked for on demand.
# =============================================================================

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import comms as comms_module
from app.core.comms import comms_configured, upsert_recipient, user_snapshot
from app.core.comms_sync import ensure_recipient
from app.core.config import settings
from app.core.events.models import OutboxEvent
from app.modules.auth.service import get_platform_user_id
from app.modules.users.models import User, UserRole
from tests.helpers import register_user

_URL = "http://comms.test"
_TOKEN = "t64-service-token"


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""


def _fake_httpx(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> list[dict]:
    """Replace app.core.comms's httpx client. Returns the call log.

    `outcome` is either a status code to answer with, or an exception
    instance to raise from put().
    """
    calls: list[dict] = []

    class _FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *exc_info: Any) -> bool:
            return False

        async def put(
            self,
            url: str,
            json: dict | None = None,
            headers: dict | None = None,
        ) -> _FakeResponse:
            calls.append(
                {
                    "url": url,
                    "json": json,
                    "headers": headers,
                    "timeout": self.kwargs.get("timeout"),
                }
            )
            if isinstance(outcome, Exception):
                raise outcome
            return _FakeResponse(outcome)

    monkeypatch.setattr(comms_module.httpx, "AsyncClient", _FakeClient)
    return calls


@pytest.fixture
def comms_configured_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the client at a comms that does not exist."""
    monkeypatch.setattr(settings, "comms_api_url", _URL)
    monkeypatch.setattr(settings, "comms_service_token", _TOKEN)


async def _make_user(session: AsyncSession, **overrides: Any) -> User:
    """A flushed user, built the way registration builds one.

    referred_by is NOT NULL with a foreign key, and production never
    leaves it unset: _resolve_referrer falls back to the platform user
    for organic sign-ups. A builder that skipped it produced a user
    this database refuses -- which is exactly what the first run of
    this suite found.

    One builder rather than a saved and an unsaved variant: an object
    that looks like a user but cannot be flushed is a trap for whoever
    writes the next test here.
    """
    user = User(
        role=UserRole.INVESTOR,
        referred_by=await get_platform_user_id(session),
        credentials=overrides.pop("credentials", {}),
        language=overrides.pop("language", "en"),
    )
    for key, value in overrides.items():
        setattr(user, key, value)
    session.add(user)
    await session.flush()
    return user


async def _outbox_ids(session: AsyncSession) -> set[int]:
    """Ids of every outbox row visible right now.

    Deltas, not absolute counts: this suite shares one database with the
    rest of the run, and an absolute assertion would be measuring
    whoever ran before it.
    """
    result = await session.execute(select(OutboxEvent.id))
    return set(result.scalars().all())


async def _rows_added_since(
    session: AsyncSession, before: set[int]
) -> list[OutboxEvent]:
    """Rows that appeared after `before` was taken, in id order.

    Filtered in python rather than with a NOT IN over the snapshot:
    the sets here are single digits, and one filter that is obviously
    right beats two that have to agree.
    """
    result = await session.execute(select(OutboxEvent).order_by(OutboxEvent.id))
    return [row for row in result.scalars().all() if row.id not in before]


# ---------------------------------------------------------------------------
# 1. The snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_is_complete_for_every_user_shape(
    db_session: AsyncSession,
) -> None:
    """Snapshot, not patch: all five fields present in every shape.

    comms overwrites what it holds with exactly this document, so a key
    that goes missing for one kind of user is not a smaller update --
    it is a rejected request (422) or, worse, a silently kept stale
    value. timezone is always present and always None: this product
    does not track one.
    """
    telegram_user = await _make_user(
        db_session, credentials={"telegram": {"id": 92180}}, language="ru"
    )
    email_user = await _make_user(
        db_session, credentials={"email": {"email": "a@example.test"}}, language="en"
    )
    bare_user = await _make_user(db_session, credentials={})

    expected_keys = {"telegram_id", "email", "locale", "timezone", "active"}
    for user in (telegram_user, email_user, bare_user):
        snapshot = user_snapshot(user)
        assert set(snapshot) == expected_keys
        assert snapshot["timezone"] is None

    assert user_snapshot(telegram_user)["telegram_id"] == 92180
    assert user_snapshot(telegram_user)["email"] is None
    assert user_snapshot(email_user)["telegram_id"] is None
    assert user_snapshot(email_user)["email"] == "a@example.test"
    assert user_snapshot(bare_user)["telegram_id"] is None

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 2. No comms configured -- no call, and no outbox row either
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_url_makes_no_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Emptiness axis: an unconfigured box must be silent, not merely
    harmless. The call log is asserted empty, so a client built 'just in
    case' fails here rather than at a DNS lookup in production."""
    monkeypatch.setattr(settings, "comms_api_url", "")
    calls = _fake_httpx(monkeypatch, 200)

    assert comms_configured() is False
    assert await upsert_recipient(uuid4(), {"active": True}) is False
    assert calls == []


@pytest.mark.asyncio
async def test_empty_url_emits_no_outbox_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no comms there is no relay either (its address is empty by
    the same hand), so an outbox row here would be a row nobody ever
    ships -- growth, not delivery."""
    monkeypatch.setattr(settings, "comms_api_url", "")
    before = await _outbox_ids(db_session)

    user = await _make_user(
        db_session, credentials={"email": {"email": "b@example.test"}}
    )

    assert await ensure_recipient(db_session, user) is False
    assert await _rows_added_since(db_session, before) == []

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 3-4. Outcomes: one success, four failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_sends_the_snapshot_and_skips_the_outbox(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    comms_configured_url: None,
) -> None:
    calls = _fake_httpx(monkeypatch, 200)
    before = await _outbox_ids(db_session)

    user = await _make_user(
        db_session, credentials={"telegram": {"id": 92181}}, language="de"
    )

    assert await ensure_recipient(db_session, user) is True

    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == f"{_URL}/api/v1/recipients/{user.id}"
    assert call["headers"]["Authorization"] == f"Bearer {_TOKEN}"
    assert call["timeout"] == settings.comms_http_timeout_seconds
    assert call["json"] == {
        "telegram_id": 92181,
        "email": None,
        "locale": "de",
        "timezone": None,
        "active": True,
    }
    assert await _rows_added_since(db_session, before) == [], (
        "the fast path needs no fallback"
    )

    await db_session.rollback()


@pytest.mark.parametrize(
    "outcome",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        401,
        500,
    ],
    ids=["refused", "timeout", "unauthorized", "server_error"],
)
@pytest.mark.asyncio
async def test_failures_never_raise(
    monkeypatch: pytest.MonkeyPatch,
    comms_configured_url: None,
    outcome: Any,
) -> None:
    """Every way comms can fail comes back as False, not as an
    exception. This is the property the caller depends on: creating a
    user must not become fragile because another service is down."""
    _fake_httpx(monkeypatch, outcome)

    assert await upsert_recipient(uuid4(), {"active": True}) is False


@pytest.mark.asyncio
async def test_failure_defers_the_recipient_to_the_outbox(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    comms_configured_url: None,
) -> None:
    """A failed fast path degrades to the slow path, not to nothing.

    The row carries recipient_id INSIDE the payload -- the HTTP call
    carries it in the path instead, and this is the one place the two
    transports differ.
    """
    _fake_httpx(monkeypatch, httpx.ConnectError("comms is down"))
    before = await _outbox_ids(db_session)

    user = await _make_user(
        db_session, credentials={"telegram": {"id": 92182}}, language="fr"
    )

    assert await ensure_recipient(db_session, user) is False

    rows = await _rows_added_since(db_session, before)
    assert len(rows) == 1
    assert rows[0].event_type == "user_upserted"
    assert rows[0].payload == {
        "v": 1,
        "recipient_id": str(user.id),
        "telegram_id": 92182,
        "email": None,
        "locale": "fr",
        "timezone": None,
        "active": True,
    }
    assert rows[0].published_at is None

    await db_session.rollback()


# ---------------------------------------------------------------------------
# 5. The whole point: registration survives comms being down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registration_succeeds_while_comms_is_down(
    client: Any,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    comms_configured_url: None,
) -> None:
    """End to end through the real route, with comms refusing.

    register_user asserts 201 itself, so the failure mode this guards
    against -- a comms outage turning into a 500 for someone trying to
    sign up -- fails the test at that assertion.
    """
    _fake_httpx(monkeypatch, httpx.ConnectError("comms is down"))
    before = await _outbox_ids(db_session)

    body = await register_user(client)
    user_id = UUID(body["user"]["id"])

    deferred = await _rows_added_since(db_session, before)
    assert len(deferred) == 1
    assert deferred[0].event_type == "user_upserted"
    assert deferred[0].payload["recipient_id"] == str(user_id)

    # Targeted cleanup: this test COMMITTED (the HTTP path does), and a
    # pending outbox row left behind would fail the relay suite's
    # empty-outbox assertion. Only the rows this test created are
    # removed.
    await db_session.execute(
        delete(OutboxEvent).where(OutboxEvent.id.in_([row.id for row in deferred]))
    )
    await db_session.commit()
