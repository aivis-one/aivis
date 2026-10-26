# =============================================================================
# AIVIS.ONE Backend -- Tests: the first password (H44)
# =============================================================================
#
# Owner's rule: an account whose e-mail is confirmed and that has no password
# must choose one before it goes on (User.password_required, surfaced on every
# UserResponse); POST /api/v1/users/me/password sets that first password and
# nothing else.
#
# THE ACCOUNT WITHOUT A PASSWORD is made the way the product makes it: the
# Mini App entry (tests/helpers.login_telegram) -- the e-mail step creates the
# row without a password, the code step confirms the e-mail and links the
# Telegram id.
#
# TWO HARNESSES, because the suite's `client` cannot see two things:
#   * the race -- two calls at once. Each call's hash_password waits on an
#     event; the harness lets them go only when either both are inside it
#     (no lock held them apart) or one is inside and another backend waits on
#     a row lock (pg_stat_activity). The colour is decided by the code, not by
#     the scheduler: without the lock both calls are always inside together.
#   * the commit against the response -- httpx's ASGITransport returns only
#     after the whole app has run, so a commit after the response looks the
#     same as one before it. The app is called through the raw ASGI interface
#     and the row is read from another session at the moment
#     `http.response.start` is sent.
#
# AXES: repeat -- the second call is a 409, the race gives one 200 and one
# 409; emptiness -- no body, an empty password, no e-mail, every form of "no
# hash"; shortage -- 7 and 129 characters refused, 8 and 128 taken.
# =============================================================================

import asyncio
import json
import secrets
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import BaseModel, ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.config import settings
from app.core.database import get_session_factory
from app.main import app
from app.modules.auth.schemas import EmailRegisterRequest, PasswordResetConfirmRequest
from app.modules.auth.service import verify_password
from app.modules.companies.schemas import CreateCompanyRequest
from app.modules.users import service as users_service
from app.modules.users.models import User
from app.modules.users.schemas import SetPasswordRequest
from tests.helpers import (
    auth_headers,
    create_admin_user,
    login_legacy_telegram,
    login_telegram,
    login_user,
    register_user,
    telegram_entry,
)

URL = "/api/v1/users/me/password"
NEW_PASSWORD = "Chosen-pass-1"


def _tg() -> int:
    """A fresh Telegram id above int32, never reused."""
    return 6_000_000_000 + secrets.randbelow(2_000_000_000)


async def _row(user_id: str) -> User:
    """The user row as committed, read through a session of its own."""
    async with get_session_factory()() as session:
        return (
            await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
        ).scalar_one()


async def _passwordless(client: AsyncClient) -> tuple[dict, int]:
    """An account from the Mini App entry: confirmed e-mail, no password.

    Returns (the code step's body -- {user, session_token} -- and the
    Telegram id). Pair: the row really is in the state the test needs.
    """
    tg_id = _tg()
    body = await login_telegram(client, telegram_id=tg_id)
    row = await _row(body["user"]["id"])
    assert row.email_verified is True
    assert row.has_password is False
    return body, tg_id


# ---------------------------------------------------------------------------
# 1. "Is there a password" -- every form of the stored credentials
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("credentials", "expected"),
    [
        ({"email": {"email": "a@example.com", "password_hash": "$argon2id$x"}}, True),
        ({"email": {"email": "a@example.com", "password_hash": ""}}, False),
        ({"email": {"email": "a@example.com", "password_hash": None}}, False),
        ({"email": {"email": "a@example.com"}}, False),
        ({"telegram": {"id": 1}}, False),
        ({"email": None}, False),
        ({}, False),
    ],
    ids=[
        "hash",
        "empty-string",
        "none",
        "no-key",
        "no-email-block",
        "email-null",
        "empty",
    ],
)
def test_has_password_reads_every_form(credentials: dict, expected: bool) -> None:
    assert User(credentials=credentials).has_password is expected


@pytest.mark.parametrize(
    ("email_block", "expected"),
    [
        ({"email": "a@example.com", "verified": True}, True),
        ({"email": "a@example.com", "verified": True, "password_hash": ""}, True),
        (
            {
                "email": "a@example.com",
                "verified": True,
                "password_hash": "$argon2id$x",
            },
            False,
        ),
        ({"email": "a@example.com", "verified": False}, False),
        (
            {
                "email": "a@example.com",
                "verified": False,
                "password_hash": "$argon2id$x",
            },
            False,
        ),
        (None, False),
    ],
    ids=[
        "confirmed-no-key",
        "confirmed-empty",
        "confirmed-with-password",
        "unconfirmed-no-password",
        "unconfirmed-with-password",
        "telegram-only",
    ],
)
def test_password_required_is_confirmed_email_and_no_password(
    email_block: dict | None, expected: bool
) -> None:
    credentials: dict[str, Any] = {"telegram": {"id": 1}}
    if email_block is not None:
        credentials["email"] = email_block
    assert User(credentials=credentials).password_required is expected


# ---------------------------------------------------------------------------
# 2. One password rule, the same for every consumer
# ---------------------------------------------------------------------------


def _password_errors(model: type[BaseModel], field: str, value: str) -> bool:
    """Whether `value` in `field` is refused (other fields may be wrong too)."""
    try:
        model.model_validate({field: value})
    except ValidationError as exc:
        return any(err["loc"] == (field,) for err in exc.errors())
    return False


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (EmailRegisterRequest, "password"),
        (PasswordResetConfirmRequest, "new_password"),
        (SetPasswordRequest, "password"),
        (CreateCompanyRequest, "password"),
    ],
    ids=["register", "reset", "first-password", "staff-company"],
)
def test_every_password_field_holds_the_same_rule(
    model: type[BaseModel], field: str
) -> None:
    assert _password_errors(model, field, "x" * 7) is True
    assert _password_errors(model, field, "x" * 8) is False
    assert _password_errors(model, field, "x" * 128) is False
    assert _password_errors(model, field, "x" * 129) is True


# ---------------------------------------------------------------------------
# 3. The flag reaches the frontend wherever the user does
# ---------------------------------------------------------------------------


async def test_flag_on_every_answer_of_an_account_without_a_password(
    client: AsyncClient,
) -> None:
    """The code step, GET /users/me and the Mini App sign-in all say true."""
    body, tg_id = await _passwordless(client)
    assert body["user"]["password_required"] is True

    me = await client.get(
        "/api/v1/users/me", headers=auth_headers(body["session_token"])
    )
    assert me.status_code == 200
    assert me.json()["password_required"] is True

    again = await telegram_entry(client, telegram_id=tg_id)
    assert again["session_token"]
    assert again["user"]["password_required"] is True


async def test_flag_is_false_for_an_unconfirmed_e_mail_with_a_password(
    client: AsyncClient,
) -> None:
    """Registration by e-mail: the e-mail is not confirmed yet -> false."""
    body = await register_user(client)
    assert body["user"]["password_required"] is False
    assert body["user"]["onboarding_step"] == "registered"


async def test_flag_is_false_for_a_telegram_only_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    body = await login_legacy_telegram(client, db_session, telegram_id=_tg())
    assert body["session_token"]
    assert body["user"]["email"] is None
    assert body["user"]["password_required"] is False


async def test_an_account_with_a_password_never_sees_the_screen(
    client: AsyncClient,
) -> None:
    """A web account with a confirmed e-mail and a password, linked to
    Telegram: false after the e-mail sign-in and after the Mini App one."""
    email = f"pw_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email, email_confirmed=True)

    by_email = await login_user(client, email=email)
    assert by_email["user"]["password_required"] is False

    tg_id = _tg()
    linked = await login_telegram(client, telegram_id=tg_id, email=email)
    assert linked["user"]["password_required"] is False
    by_telegram = await telegram_entry(client, telegram_id=tg_id)
    assert by_telegram["session_token"]
    assert by_telegram["user"]["password_required"] is False


# ---------------------------------------------------------------------------
# 4. POST /users/me/password
# ---------------------------------------------------------------------------


async def test_sets_the_first_password_and_the_account_signs_in_by_it(
    client: AsyncClient,
) -> None:
    body, tg_id = await _passwordless(client)
    # A second session of the same account, opened before the password.
    other = await telegram_entry(client, telegram_id=tg_id)

    resp = await client.post(
        URL,
        json={"password": NEW_PASSWORD},
        headers=auth_headers(body["session_token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["password_required"] is False
    assert resp.json()["id"] == body["user"]["id"]

    row = await _row(body["user"]["id"])
    assert await verify_password(
        NEW_PASSWORD, row.credentials["email"]["password_hash"]
    )
    assert row.email_verified is True

    # The other session lives on.
    me = await client.get(
        "/api/v1/users/me", headers=auth_headers(other["session_token"])
    )
    assert me.status_code == 200
    assert me.json()["password_required"] is False

    # The account signs in by e-mail with the new password, and in the Mini
    # App the screen is gone too.
    login = await login_user(client, email=row.email, password=NEW_PASSWORD)
    assert login["user"]["password_required"] is False
    by_telegram = await telegram_entry(client, telegram_id=tg_id)
    assert by_telegram["user"]["password_required"] is False

    async with get_session_factory()() as session:
        events = (
            (
                await session.execute(
                    select(AuditLog.event).where(
                        AuditLog.target_id == uuid.UUID(body["user"]["id"]),
                        AuditLog.event == "user.password_set",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert events == ["user.password_set"]


async def test_a_second_call_is_a_409_and_keeps_the_first_password(
    client: AsyncClient,
) -> None:
    body, _tg_id = await _passwordless(client)
    headers = auth_headers(body["session_token"])
    first = await client.post(URL, json={"password": NEW_PASSWORD}, headers=headers)
    assert first.status_code == 200

    second = await client.post(
        URL, json={"password": "Another-pass-2"}, headers=headers
    )
    assert second.status_code == 409
    assert second.json()["error"] == "password_already_set"

    row = await _row(body["user"]["id"])
    assert await verify_password(
        NEW_PASSWORD, row.credentials["email"]["password_hash"]
    )


async def test_an_account_with_a_password_is_refused(client: AsyncClient) -> None:
    """Confirmed or not, an account that has a password gets 409; the
    password is checked before the e-mail."""
    for confirmed in (True, False):
        body = await register_user(client, email_confirmed=confirmed)
        resp = await client.post(
            URL,
            json={"password": NEW_PASSWORD},
            headers=auth_headers(body["session_token"]),
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "password_already_set"


async def test_no_e_mail_or_an_unconfirmed_one_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A Telegram-only account (no e-mail), then the same account with an
    e-mail added but not confirmed: 409 email_not_verified, nothing written."""
    body = await login_legacy_telegram(client, db_session, telegram_id=_tg())
    headers = auth_headers(body["session_token"])

    resp = await client.post(URL, json={"password": NEW_PASSWORD}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"] == "email_not_verified"

    attached = await client.post(
        "/api/v1/users/me/email",
        json={"email": f"att_{uuid.uuid4().hex[:12]}@example.com"},
        headers=headers,
    )
    assert attached.status_code == 200
    resp = await client.post(URL, json={"password": NEW_PASSWORD}, headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"] == "email_not_verified"

    row = await _row(body["user"]["id"])
    assert row.email is not None
    assert row.has_password is False


@pytest.mark.parametrize(
    "payload",
    [{}, {"password": ""}, {"password": "x" * 7}, {"password": "x" * 129}],
    ids=["no-body-field", "empty", "seven", "one-twenty-nine"],
)
async def test_a_password_outside_the_rule_is_a_422(
    client: AsyncClient, payload: dict
) -> None:
    body, _tg_id = await _passwordless(client)
    resp = await client.post(
        URL, json=payload, headers=auth_headers(body["session_token"])
    )
    assert resp.status_code == 422
    assert (await _row(body["user"]["id"])).has_password is False


@pytest.mark.parametrize("length", [8, 128])
async def test_the_bounds_of_the_rule_are_taken(
    client: AsyncClient, length: int
) -> None:
    body, _tg_id = await _passwordless(client)
    password = "p" * length
    resp = await client.post(
        URL, json={"password": password}, headers=auth_headers(body["session_token"])
    )
    assert resp.status_code == 200
    row = await _row(body["user"]["id"])
    assert await verify_password(password, row.credentials["email"]["password_hash"])


async def test_without_a_session_is_a_401(client: AsyncClient) -> None:
    resp = await client.post(URL, json={"password": NEW_PASSWORD})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. Avatar mode: the shared switch decides, both ways
# ---------------------------------------------------------------------------


async def _avatar_into_passwordless(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[str, str]:
    """(avatar session token, the target's user id)."""
    _admin, admin_token = await create_admin_user(client, db_session)
    body, _tg_id = await _passwordless(client)
    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": body["user"]["id"]},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["session_token"], body["user"]["id"]


async def test_avatar_is_refused_when_the_restrictions_are_on(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "avatar_restrictions_enabled", True)
    token, user_id = await _avatar_into_passwordless(client, db_session)

    resp = await client.post(
        URL, json={"password": NEW_PASSWORD}, headers=auth_headers(token)
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()
    assert (await _row(user_id)).has_password is False


async def test_avatar_passes_while_the_restrictions_are_off(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shipped default (owner-ruled 2026-08-17): every guarded operation
    is open to an avatar, this one included."""
    monkeypatch.setattr(settings, "avatar_restrictions_enabled", False)
    token, user_id = await _avatar_into_passwordless(client, db_session)

    resp = await client.post(
        URL, json={"password": NEW_PASSWORD}, headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert (await _row(user_id)).has_password is True


# ---------------------------------------------------------------------------
# 6. Two calls at once: one password, one refusal
# ---------------------------------------------------------------------------


async def _lock_waiters() -> int:
    """Backends of this database waiting on a lock right now."""
    async with get_session_factory()() as session:
        return (
            await session.execute(
                text(
                    "select count(*) from pg_stat_activity "
                    "where datname = current_database() and wait_event_type = 'Lock'"
                )
            )
        ).scalar_one()


async def test_two_calls_at_once_give_one_password_and_one_409(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE INVARIANT, NOT THE WINNER: one 200 and one 409, and the stored
    hash is the 200's password. A deadlock fails it: under FOR SHARE in
    place of FOR NO KEY UPDATE both calls hold the share lock, both reach
    the write, and Postgres breaks the cycle (DeadlockDetectedError)."""
    body, _tg_id = await _passwordless(client)
    headers = auth_headers(body["session_token"])

    real_hash = users_service.hash_password
    inside = 0
    release = asyncio.Event()

    async def held_hash(password: str) -> str:
        nonlocal inside
        inside += 1
        await release.wait()
        return await real_hash(password)

    monkeypatch.setattr(users_service, "hash_password", held_hash)

    passwords = ("First-pass-111", "Second-pass-222")
    calls = [
        asyncio.create_task(client.post(URL, json={"password": p}, headers=headers))
        for p in passwords
    ]

    # Let them go once the order is decided: both inside the hash (nothing
    # held them apart), or one inside and the other waiting on the row lock.
    for _ in range(400):
        if inside >= 2 or (inside == 1 and await _lock_waiters() >= 1):
            break
        await asyncio.sleep(0.025)
    else:
        release.set()
        await asyncio.gather(*calls, return_exceptions=True)
        pytest.fail(f"the two calls never met: inside={inside}")
    release.set()
    responses = await asyncio.gather(*calls)

    assert sorted(r.status_code for r in responses) == [200, 409], [
        r.text for r in responses
    ]
    loser = next(r for r in responses if r.status_code == 409)
    assert loser.json()["error"] == "password_already_set"
    winner = passwords[[r.status_code for r in responses].index(200)]
    row = await _row(body["user"]["id"])
    assert await verify_password(winner, row.credentials["email"]["password_hash"])


# ---------------------------------------------------------------------------
# 7. The password is committed before the answer leaves
# ---------------------------------------------------------------------------


async def _call_raw(token: str, payload: dict, on_start: Any) -> list[int]:
    """POST /users/me/password through the raw ASGI interface.

    `on_start` runs at the moment http.response.start is sent -- the moment
    a real server puts the status on the wire.
    """
    statuses: list[int] = []
    raw = json.dumps(payload).encode()
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            await asyncio.sleep(3600)
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])
            await on_start()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": URL,
        "raw_path": URL.encode(),
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(raw)).encode()),
            (b"authorization", f"Bearer {token}".encode()),
        ],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "root_path": "",
    }
    await app(scope, receive, send)
    return statuses


async def test_the_password_is_committed_when_the_answer_starts(
    client: AsyncClient,
) -> None:
    """get_db_session commits only after the response is sent; this route
    commits itself first (users/router.py, P-01's second exception). Read
    from another session at http.response.start, the row has the hash."""
    body, _tg_id = await _passwordless(client)
    seen: list[bool] = []

    async def on_start() -> None:
        seen.append((await _row(body["user"]["id"])).has_password)

    statuses = await _call_raw(
        body["session_token"], {"password": NEW_PASSWORD}, on_start
    )

    assert statuses == [200]
    assert seen == [True]
