# =============================================================================
# AIVIS.ONE Backend -- Telegram entry: the link of a Telegram id to an account
# =============================================================================
#
# Tests of "one person, one account" (POST /auth/telegram is
# find-only; POST /auth/telegram/link/email and /confirm prove the mailbox and
# link the Telegram id). One section per misuse of the entry
# and per rule of the code step:
#
#   find-only       an unknown Telegram id gets link_required and creates no row
#   threat 1        squat: a web row never verified is claimed by the proof
#   threat 2        a second Telegram on an e-mail account is refused
#   threat 3        a Telegram account never reaches the e-mail step again
#   threat 4        stale / foreign initData cannot reach the link endpoints
#                   (the replay key itself: test_telegram_entry_unit.py)
#   threat 5        brute force: tries counted per e-mail, lock, hourly codes
#   threat 6        the e-mail step answers one word for every e-mail
#   threat 7        two-factor: the second code in the same call
#   threat 8        blocked / self-deactivated refused, staff allowed
#   threat 9        no one's session ends on a link of a verified row
#   threat 11       distinct e-mails per day per Telegram id, per-IP daily cap
#   threat 13       two taps race: one lock, one winner
#   threat 14       the link token: single use, live only while it is live
#   threat 16       the two letters name the Telegram account
#   consent         the server signs cabinet_terms and privacy_policy
#   prover referral  referral of the prover
#   comms           sync_recipient after the Telegram id is written
#
# These need the dedicated test database and Redis like the rest of the suite.
# =============================================================================

import asyncio
import hashlib
import json
import secrets
import uuid
from typing import Any

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from app.modules.auth import service as auth_service
from app.modules.auth.service import get_platform_user_id
from app.modules.documents.models import Document, DocumentSigning, DocumentStatus
from app.modules.users.models import User
from tests.helpers import (
    auth_headers,
    build_init_data,
    confirm_email,
    create_admin_user,
    create_agent_with_link,
    create_staff_user,
    link_telegram_confirm,
    link_telegram_email,
    login_legacy_telegram,
    login_telegram,
    read_telegram_link_code,
    register_user,
    telegram_entry,
)

pytestmark = pytest.mark.asyncio

ASK_ANSWER = {"status": "code_sent", "code_ttl_minutes": 10}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _tg() -> int:
    """A fresh Telegram id above int32, never reused."""
    return 5_000_000_000 + secrets.randbelow(4_000_000_000)


def _email() -> str:
    return f"link_{uuid.uuid4().hex[:12]}@example.com"


def _wrong_code(real: str) -> str:
    return "000000" if real != "000000" else "000001"


async def _start(
    client: AsyncClient,
    telegram_id: int | None = None,
    **kwargs: Any,
) -> str:
    """POST /auth/telegram for an unknown id; returns the link token."""
    body = await telegram_entry(client, telegram_id=telegram_id or _tg(), **kwargs)
    assert body["link_required"] is True, body
    assert body["link_token"]
    return body["link_token"]


async def _flow(
    client: AsyncClient,
    email: str,
    *,
    telegram_id: int | None = None,
    consent: bool = True,
    referral_code: str | None = None,
    second_code: str | None = None,
    headers: dict[str, str] | None = None,
    **entry: Any,
) -> tuple[str, str, Any]:
    """Entry -> e-mail step -> code step. Returns (token, code, confirm response)."""
    token = await _start(client, telegram_id, referral_code=referral_code, **entry)
    ask = await link_telegram_email(
        client, token, email, consent_given=consent, referral_code=referral_code
    )
    assert ask.status_code == 200, ask.text
    code = await read_telegram_link_code(token)
    resp = await link_telegram_confirm(
        client, token, code, second_code=second_code, headers=headers
    )
    return token, code, resp


async def _load(db: AsyncSession, email: str) -> User:
    return (
        await db.execute(
            select(User)
            .where(User.credentials["email"]["email"].as_string() == email)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _count_by_email(db: AsyncSession, email: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.credentials["email"]["email"].as_string() == email)
        )
    ).scalar_one()


async def _count_by_telegram(db: AsyncSession, telegram_id: int) -> int:
    from sqlalchemy import BigInteger, cast

    return (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(
                cast(User.credentials["telegram"]["id"].astext, BigInteger)
                == telegram_id
            )
        )
    ).scalar_one()


async def _verified_web_user(
    client: AsyncClient, **kwargs: Any
) -> tuple[str, str, dict]:
    """A web account with a PROVEN e-mail: (email, password, register body)."""
    email = _email()
    password = "Password123!"
    body = await register_user(client, email=email, password=password, **kwargs)
    await confirm_email(body["user"]["id"])
    return email, password, body


async def _set_account(
    db: AsyncSession, email: str, *, active: bool, self_deactivated: bool = False
) -> None:
    user = await _load(db, email)
    user.is_active = active
    creds = dict(user.credentials)
    if self_deactivated:
        creds["account"] = {"deactivated_by": "self"}
    user.set_jsonb("credentials", creds)
    await db.commit()


async def _enable_totp(client: AsyncClient, token: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"current_password": password},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    secret = resp.json()["secret"]
    resp = await client.post(
        "/api/v1/auth/2fa/confirm",
        json={"code": pyotp.TOTP(secret).now()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return secret


async def _session_alive(client: AsyncClient, token: str) -> bool:
    resp = await client.get("/api/v1/auth/sessions", headers=auth_headers(token))
    return resp.status_code == 200


async def _ensure_consent_documents(db: AsyncSession) -> dict[str, uuid.UUID]:
    """The two documents of the consent screen, active, in English.

    Taken from the database when the seed put them there; made (not
    required for any role, so no other test is touched) when it did not.
    """
    platform_id = await get_platform_user_id(db)
    ids: dict[str, uuid.UUID] = {}
    for doc_type in ("cabinet_terms", "privacy_policy"):
        doc = (
            (
                await db.execute(
                    select(Document)
                    .where(
                        Document.type == doc_type,
                        Document.language == "en",
                        Document.status == DocumentStatus.ACTIVE,
                    )
                    .order_by(Document.version.desc())
                )
            )
            .scalars()
            .first()
        )
        if doc is None:
            top = (
                await db.execute(
                    select(func.max(Document.version)).where(
                        Document.type == doc_type, Document.language == "en"
                    )
                )
            ).scalar() or 0
            doc = Document(
                type=doc_type,
                version=top + 1,
                language="en",
                title=doc_type,
                required_for_roles=[],
                content_hash="test",
                status=DocumentStatus.ACTIVE,
                created_by=platform_id,
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
        ids[doc_type] = doc.id
    return ids


class Recorder:
    """Stands in for emit_event: keeps every payload it is handed."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def __call__(self, session: Any, event_type: str, data: dict) -> None:
        self.payloads.append(data)

    def of_type(self, letter_type: str) -> list[dict[str, Any]]:
        return [p for p in self.payloads if p["type"] == letter_type]


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    monkeypatch.setattr(auth_service, "emit_event", rec)
    monkeypatch.setattr(auth_service, "comms_configured", lambda: True)
    return rec


# ---------------------------------------------------------------------------
# POST /auth/telegram is find-only (B-1)
# ---------------------------------------------------------------------------


async def test_unknown_telegram_id_gets_link_required_and_no_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tg_id = _tg()
    body = await telegram_entry(client, telegram_id=tg_id, first_name="Newcomer")

    assert body["link_required"] is True
    assert body["link_token"]
    assert body["session_token"] is None
    assert body["user"] is None
    assert body["mfa_required"] is False
    assert await _count_by_telegram(db_session, tg_id) == 0

    # The token is held in Redis for 15 minutes, bound to this Telegram id.
    key = f"telegram_link:{body['link_token']}"
    ttl = await get_redis().ttl(key)
    assert 0 < ttl <= settings.telegram_link_token_ttl_seconds
    record = json.loads(await get_redis().get(key))
    assert record["telegram"]["id"] == tg_id
    assert record["consent_given"] is False


async def test_returning_linked_person_logs_in_with_no_link_step(
    client: AsyncClient,
) -> None:
    tg_id = _tg()
    first = await login_telegram(client, telegram_id=tg_id)
    again = await telegram_entry(client, telegram_id=tg_id)

    assert again["link_required"] is False
    assert again["link_token"] is None
    assert again["user"]["id"] == first["user"]["id"]
    assert again["session_token"]


async def test_old_telegram_only_row_still_logs_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A row born before the change (no e-mail) is found, not re-linked."""
    body = await login_legacy_telegram(client, db_session, telegram_id=_tg())
    assert body["link_required"] is False
    assert body["session_token"]


# ---------------------------------------------------------------------------
# Threat 1 -- a squat on the e-mail is claimed by the proof of the mailbox
# ---------------------------------------------------------------------------


async def test_threat1_unverified_web_row_is_claimed_by_the_mailbox_proof(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    victim_email = _email()
    attacker_password = "AttackerPass1!"
    attacker = await register_user(
        client, email=victim_email, password=attacker_password
    )
    attacker_token = attacker["session_token"]
    secret = await _enable_totp(client, attacker_token, attacker_password)
    assert secret
    assert await _session_alive(client, attacker_token)

    tg_id = _tg()
    _token, _code, resp = await _flow(client, victim_email, telegram_id=tg_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["session_token"]

    user = await _load(db_session, victim_email)
    assert user.email_verified is True
    assert "password_hash" not in user.credentials["email"]
    assert not user.credentials.get("totp")
    assert user.credentials["telegram"]["id"] == tg_id

    # The attacker's password no longer opens the account ...
    login = await client.post(
        "/api/v1/auth/email/login",
        json={"email": victim_email, "password": attacker_password},
    )
    assert login.status_code == 401
    # ... and the session he already held is gone.
    assert not await _session_alive(client, attacker_token)


async def test_threat1_staff_blocked_unverified_row_is_refused_and_untouched(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A staff block is not a self-deactivation: support decides. The claim
    that ran before the refusal is rolled back with the transaction."""
    email = _email()
    await register_user(client, email=email, password="AttackerPass1!")
    await _set_account(db_session, email, active=False)

    tg_id = _tg()
    _token, _code, resp = await _flow(client, email, telegram_id=tg_id)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"] == "account_blocked"

    user = await _load(db_session, email)
    assert user.credentials["email"].get("password_hash")
    assert user.email_verified is False
    assert "telegram" not in user.credentials
    assert user.is_active is False


async def test_threat1_self_deactivation_of_an_unproven_holder_is_dropped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email = _email()
    await register_user(client, email=email, password="AttackerPass1!")
    await _set_account(db_session, email, active=False, self_deactivated=True)

    _token, _code, resp = await _flow(client, email)
    assert resp.status_code == 200, resp.text
    user = await _load(db_session, email)
    assert user.is_active is True
    assert "account" not in user.credentials


# ---------------------------------------------------------------------------
# Threat 2 -- a second Telegram on an e-mail account
# ---------------------------------------------------------------------------


async def test_threat2_second_telegram_is_refused_after_the_proof(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email, _password, _body = await _verified_web_user(client)
    tg_a, tg_b = _tg(), _tg()

    _t, _c, first = await _flow(client, email, telegram_id=tg_a)
    assert first.status_code == 200, first.text

    _t, _c, second = await _flow(client, email, telegram_id=tg_b)
    assert second.status_code == 403, second.text
    assert second.json()["error"] == "telegram_conflict"

    user = await _load(db_session, email)
    assert user.credentials["telegram"]["id"] == tg_a
    assert await _count_by_telegram(db_session, tg_b) == 0


# ---------------------------------------------------------------------------
# Threat 3 -- a Telegram account never gets a second e-mail
# ---------------------------------------------------------------------------


async def test_threat3_linked_telegram_never_reaches_the_email_step(
    client: AsyncClient,
) -> None:
    tg_id = _tg()
    first = await login_telegram(client, telegram_id=tg_id)

    # The entry finds the row: no link token, so no e-mail step to use.
    again = await telegram_entry(client, telegram_id=tg_id)
    assert again["link_required"] is False
    assert again["link_token"] is None

    # No endpoint changes an e-mail: adding one to an account that has one
    # is refused.
    resp = await client.post(
        "/api/v1/users/me/email",
        json={"email": _email()},
        headers=auth_headers(first["session_token"]),
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] == "email_already_set"


# ---------------------------------------------------------------------------
# Threat 4 -- stale or foreign initData; the link endpoints take only the token
# ---------------------------------------------------------------------------


async def test_threat4_link_endpoints_do_not_take_init_data(
    client: AsyncClient,
) -> None:
    init_data = build_init_data(telegram_id=_tg())
    resp = await client.post(
        "/api/v1/auth/telegram/link/email",
        json={"init_data": init_data, "email": _email(), "consent_given": True},
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/auth/telegram/link/confirm",
        json={"init_data": init_data, "code": "123456"},
    )
    assert resp.status_code == 422


async def test_threat4_reordered_init_data_is_a_replay(client: AsyncClient) -> None:
    from urllib.parse import parse_qsl, urlencode

    init_data = build_init_data(telegram_id=_tg())
    first = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert first.status_code == 200

    reordered = urlencode(list(reversed(parse_qsl(init_data))))
    second = await client.post("/api/v1/auth/telegram", json={"init_data": reordered})
    assert second.status_code == 400
    assert "already used" in second.json()["message"]


async def test_threat4_repeated_key_is_refused(client: AsyncClient) -> None:
    from urllib.parse import parse_qsl

    init_data = build_init_data(telegram_id=_tg())
    doubled = f"{init_data}&hash={dict(parse_qsl(init_data))['hash']}"
    resp = await client.post("/api/v1/auth/telegram", json={"init_data": doubled})
    assert resp.status_code == 400
    assert "Repeated key" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Threat 5 -- brute force of the 6-digit code
# ---------------------------------------------------------------------------


async def test_threat5_wrong_tries_count_per_email_across_tokens_and_lock(
    client: AsyncClient,
) -> None:
    email = _email()
    max_wrong = settings.telegram_link_max_wrong_codes

    # Two wrong tries on the first token.
    tok1 = await _start(client)
    assert (await link_telegram_email(client, tok1, email)).status_code == 200
    real1 = await read_telegram_link_code(tok1)
    for _ in range(2):
        resp = await link_telegram_confirm(client, tok1, _wrong_code(real1))
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_code"

    # Another Telegram account, a new code for the same e-mail: the tries
    # already made are NOT reset by it.
    tok2 = await _start(client)
    assert (await link_telegram_email(client, tok2, email)).status_code == 200
    real2 = await read_telegram_link_code(tok2)
    for _ in range(max_wrong - 2):
        resp = await link_telegram_confirm(client, tok2, _wrong_code(real2))
        assert resp.status_code == 400

    # The token that made the last allowed wrong try is gone, even for its
    # right code ...
    resp = await link_telegram_confirm(client, tok2, real2)
    assert resp.status_code == 400
    assert resp.json()["error"] == "link_token_invalid"

    # ... the e-mail is locked, so the right code of the other, still live
    # token is refused too ...
    resp = await link_telegram_confirm(client, tok1, real1)
    assert resp.status_code == 429
    assert resp.json()["error"] == "telegram_link_locked"

    # ... and no new code is sent to a locked e-mail.
    tok3 = await _start(client)
    resp = await link_telegram_email(client, tok3, email)
    assert resp.status_code == 429
    assert resp.json()["error"] == "telegram_link_locked"


async def test_threat5_new_codes_per_email_are_limited_per_hour(
    client: AsyncClient,
) -> None:
    email = _email()
    limit = settings.telegram_link_codes_per_hour
    assert limit < settings.auth_rate_limit_max_requests  # IP limit is not the cap here

    for _ in range(limit):
        tok = await _start(client)
        assert (await link_telegram_email(client, tok, email)).status_code == 200

    tok = await _start(client)
    resp = await link_telegram_email(client, tok, email)
    assert resp.status_code == 429
    assert resp.json()["error"] == "rate_limit_exceeded"


async def test_threat5_an_expired_code_is_refused_and_costs_no_try(
    client: AsyncClient,
) -> None:
    tok = await _start(client)
    assert (await link_telegram_email(client, tok, _email())).status_code == 200
    code = await read_telegram_link_code(tok)

    key = f"telegram_link:{tok}"
    record = json.loads(await get_redis().get(key))
    record["code_expires_at"] = "2000-01-01T00:00:00+00:00"
    await get_redis().set(key, json.dumps(record), keepttl=True)

    resp = await link_telegram_confirm(client, tok, code)
    assert resp.status_code == 400
    assert resp.json()["error"] == "code_expired"


# ---------------------------------------------------------------------------
# Threat 6 -- one answer for every e-mail
# ---------------------------------------------------------------------------


async def test_threat6_email_step_answers_one_word_for_every_email(
    client: AsyncClient, db_session: AsyncSession, recorder: Recorder
) -> None:
    unknown = _email()
    verified, _pw, _b = await _verified_web_user(client)
    blocked, _pw2, _b2 = await _verified_web_user(client)
    await _set_account(db_session, blocked, active=False)
    linked, _pw3, _b3 = await _verified_web_user(client)
    _t, _c, done = await _flow(client, linked, telegram_id=_tg())
    assert done.status_code == 200
    recorder.payloads.clear()

    answers = []
    for address in (unknown, verified, blocked, linked):
        tok = await _start(client)
        resp = await link_telegram_email(client, tok, address)
        assert resp.status_code == 200, resp.text
        answers.append(resp.json())

    assert answers == [ASK_ANSWER] * 4
    # A letter was queued in every branch before the answer.
    assert len(recorder.payloads) == 4


async def test_threat6_a_conflict_is_told_only_after_the_proof(
    client: AsyncClient,
) -> None:
    """The e-mail step of a row holding another Telegram id says nothing;
    the refusal comes at the code step."""
    email, _pw, _b = await _verified_web_user(client)
    _t, _c, first = await _flow(client, email, telegram_id=_tg())
    assert first.status_code == 200

    tok = await _start(client)
    ask = await link_telegram_email(client, tok, email)
    assert ask.status_code == 200
    assert ask.json() == ASK_ANSWER
    resp = await link_telegram_confirm(client, tok, _wrong_code("x"))
    assert resp.json()["error"] == "invalid_code"  # still nothing told


# ---------------------------------------------------------------------------
# Threat 7 -- two-factor
# ---------------------------------------------------------------------------


async def test_threat7_link_needs_the_second_code_in_the_same_call(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email, password, body = await _verified_web_user(client)
    secret = await _enable_totp(client, body["session_token"], password)
    tg_id = _tg()

    tok = await _start(client, tg_id)
    assert (await link_telegram_email(client, tok, email)).status_code == 200
    code = await read_telegram_link_code(tok)

    missing = await link_telegram_confirm(client, tok, code)
    assert missing.status_code == 400
    assert missing.json()["error"] == "second_code_required"
    # Asking for the second code is not a wrong try.
    tries_key = f"telegram_link_tries:{hashlib.sha256(email.encode()).hexdigest()}"
    assert int(await get_redis().get(tries_key) or 0) == 0

    wrong_second = "000000" if pyotp.TOTP(secret).now() != "000000" else "000001"
    wrong = await link_telegram_confirm(client, tok, code, second_code=wrong_second)
    assert wrong.status_code == 400
    assert wrong.json()["error"] == "second_code_invalid"

    user = await _load(db_session, email)
    assert "telegram" not in user.credentials  # nothing linked yet

    right = await link_telegram_confirm(
        client, tok, code, second_code=pyotp.TOTP(secret).now()
    )
    assert right.status_code == 200, right.text
    assert right.json()["session_token"]

    user = await _load(db_session, email)
    assert user.credentials["telegram"]["id"] == tg_id

    # A returning login of a two-factor row still answers mfa_required.
    again = await telegram_entry(client, telegram_id=tg_id)
    assert again["mfa_required"] is True
    assert again["mfa_token"]
    assert again["session_token"] is None


# ---------------------------------------------------------------------------
# Threat 8 -- inactive rows; the platform role is refused; staff are allowed
# ---------------------------------------------------------------------------


async def test_threat8_blocked_row_is_refused_at_the_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email, _pw, _b = await _verified_web_user(client)
    await _set_account(db_session, email, active=False)

    tg_id = _tg()
    _t, _c, resp = await _flow(client, email, telegram_id=tg_id)
    assert resp.status_code == 403
    assert resp.json()["error"] == "account_blocked"
    assert await _count_by_telegram(db_session, tg_id) == 0


async def test_threat8_self_deactivated_row_is_refused_at_the_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email, _pw, _b = await _verified_web_user(client)
    await _set_account(db_session, email, active=False, self_deactivated=True)

    tg_id = _tg()
    _t, _c, resp = await _flow(client, email, telegram_id=tg_id)
    assert resp.status_code == 403
    assert resp.json()["error"] == "account_self_deactivated"
    assert await _count_by_telegram(db_session, tg_id) == 0


async def test_threat8_staff_block_after_a_self_deactivation_still_reads_as_a_block(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """self-deactivate, unblock, block by staff, then claim through Telegram:
    the stale `self` marker must not make the block look like the user's own
    choice (and so must not be lifted by the claim)."""
    email = _email()
    await register_user(client, email=email, password="AttackerPass1!")
    await _set_account(db_session, email, active=False, self_deactivated=True)
    await _set_account(db_session, email, active=True)  # unblocked

    _admin, admin_token = await create_admin_user(client, db_session)
    target = await _load(db_session, email)
    resp = await client.patch(
        f"/api/v1/staff/users/{target.id}/block",
        json={"reason": "Blocked by support for the test."},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204, resp.text
    row = await _load(db_session, email)
    assert row.is_active is False
    assert row.credentials["account"]["deactivated_by"] == "staff"

    _t, _c, resp = await _flow(client, email)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"] == "account_blocked"
    assert (await _load(db_session, email)).is_active is False


@pytest.mark.parametrize(
    ("self_deactivated", "error"),
    [(False, "account_blocked"), (True, "account_self_deactivated")],
)
async def test_threat8_returning_login_of_an_inactive_row_gets_no_session(
    client: AsyncClient,
    db_session: AsyncSession,
    self_deactivated: bool,
    error: str,
) -> None:
    email = _email()
    tg_id = _tg()
    body = await login_telegram(client, telegram_id=tg_id, email=email)
    assert body["session_token"]
    await _set_account(
        db_session, email, active=False, self_deactivated=self_deactivated
    )

    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": build_init_data(telegram_id=tg_id)},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"] == error
    assert "session_token" not in resp.json() or not resp.json()["session_token"]


async def test_threat8_staff_account_may_link_like_any_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Decided by the owner, 2026-10-25: support staff work through Telegram."""
    email = _email()
    staff, _token = await create_staff_user(client, db_session, email=email)
    await confirm_email(staff.id)

    tg_id = _tg()
    _t, _c, resp = await _flow(client, email, telegram_id=tg_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["role"] == "staff"
    assert resp.json()["session_token"]

    again = await telegram_entry(client, telegram_id=tg_id)
    assert again["link_required"] is False
    assert again["session_token"]


async def _platform_row(db: AsyncSession) -> tuple[User, dict]:
    platform = (
        await db.execute(
            select(User)
            .where(User.role == "platform")
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return platform, dict(platform.credentials or {})


async def test_threat8_platform_role_is_refused_at_the_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The system's technical account never gets a Telegram session; same
    refusal as the web login (decided by the owner, 2026-10-25)."""
    platform, original = await _platform_row(db_session)
    email = _email()
    try:
        platform.set_jsonb(
            "credentials",
            {"email": {"email": email, "verified": True, "verified_at": None}},
        )
        await db_session.commit()

        tg_id = _tg()
        _t, _c, resp = await _flow(client, email, telegram_id=tg_id)
        assert resp.status_code == 401, resp.text
        assert resp.json()["message"] == "Invalid email or password"
        assert await _count_by_telegram(db_session, tg_id) == 0
    finally:
        platform, _ = await _platform_row(db_session)
        platform.set_jsonb("credentials", original)
        await db_session.commit()


async def test_threat8_platform_role_is_refused_at_the_returning_login(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    platform, original = await _platform_row(db_session)
    tg_id = _tg()
    try:
        creds = dict(original)
        creds["telegram"] = {"id": tg_id, "username": None}
        platform.set_jsonb("credentials", creds)
        await db_session.commit()

        resp = await client.post(
            "/api/v1/auth/telegram",
            json={"init_data": build_init_data(telegram_id=tg_id)},
        )
        assert resp.status_code == 401, resp.text
        assert resp.json()["message"] == "Invalid email or password"
        assert not resp.json().get("session_token")
    finally:
        platform, _ = await _platform_row(db_session)
        platform.set_jsonb("credentials", original)
        await db_session.commit()


# ---------------------------------------------------------------------------
# Threat 9 -- sessions
# ---------------------------------------------------------------------------


async def test_threat9_linking_a_verified_row_ends_no_ones_session(
    client: AsyncClient,
) -> None:
    email, _pw, body = await _verified_web_user(client)
    owner_token = body["session_token"]

    _t, _c, resp = await _flow(client, email)
    assert resp.status_code == 200, resp.text
    assert await _session_alive(client, owner_token)
    assert resp.json()["session_token"] != owner_token


# ---------------------------------------------------------------------------
# Threat 11 -- mailbox bombing
# ---------------------------------------------------------------------------


async def test_threat11_distinct_emails_per_day_per_telegram_id(
    client: AsyncClient,
) -> None:
    limit = settings.telegram_link_emails_per_day
    assert limit < settings.auth_rate_limit_max_requests
    tok = await _start(client)

    for _ in range(limit):
        assert (await link_telegram_email(client, tok, _email())).status_code == 200

    resp = await link_telegram_email(client, tok, _email())
    assert resp.status_code == 429
    assert resp.json()["error"] == "telegram_link_emails_per_day"


async def test_threat11_same_telegram_id_with_a_new_token_is_still_counted(
    client: AsyncClient,
) -> None:
    """The cap is by Telegram id, not by link token: reopening the Mini App
    mints a new token and must not mint a new allowance."""
    limit = settings.telegram_link_emails_per_day
    tg_id = _tg()
    for _ in range(limit):
        tok = await _start(client, tg_id)
        assert (await link_telegram_email(client, tok, _email())).status_code == 200

    tok = await _start(client, tg_id)
    resp = await link_telegram_email(client, tok, _email())
    assert resp.status_code == 429


async def test_threat11_per_ip_daily_cap(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_link_ip_per_day", 1)
    tok1 = await _start(client)
    assert (await link_telegram_email(client, tok1, _email())).status_code == 200
    tok2 = await _start(client)
    resp = await link_telegram_email(client, tok2, _email())
    assert resp.status_code == 429
    assert resp.json()["error"] == "rate_limit_exceeded"


# ---------------------------------------------------------------------------
# Threat 13 -- two taps race
# ---------------------------------------------------------------------------


async def test_threat13_two_telegrams_proving_one_mailbox_have_one_winner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email, _pw, _b = await _verified_web_user(client)
    tg_a, tg_b = _tg(), _tg()

    tok_a, tok_b = await _start(client, tg_a), await _start(client, tg_b)
    for tok in (tok_a, tok_b):
        assert (await link_telegram_email(client, tok, email)).status_code == 200
    code_a = await read_telegram_link_code(tok_a)
    code_b = await read_telegram_link_code(tok_b)

    resp_a, resp_b = await asyncio.gather(
        link_telegram_confirm(client, tok_a, code_a),
        link_telegram_confirm(client, tok_b, code_b),
    )
    assert sorted([resp_a.status_code, resp_b.status_code]) == [200, 403]

    user = await _load(db_session, email)
    winner = tg_a if resp_a.status_code == 200 else tg_b
    assert user.credentials["telegram"]["id"] == winner


async def test_threat13_one_telegram_id_on_two_rows_has_one_winner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two taps of the same Telegram account with two different e-mails: the
    unique index on the Telegram id decides, the loser is told to open the
    app again."""
    tg_id = _tg()
    email_1, email_2 = _email(), _email()
    tok_1, tok_2 = await _start(client, tg_id), await _start(client, tg_id)
    assert (await link_telegram_email(client, tok_1, email_1)).status_code == 200
    assert (await link_telegram_email(client, tok_2, email_2)).status_code == 200
    code_1 = await read_telegram_link_code(tok_1)
    code_2 = await read_telegram_link_code(tok_2)

    resp_1, resp_2 = await asyncio.gather(
        link_telegram_confirm(client, tok_1, code_1),
        link_telegram_confirm(client, tok_2, code_2),
    )
    assert sorted([resp_1.status_code, resp_2.status_code]) == [200, 409]
    loser = resp_2 if resp_1.status_code == 200 else resp_1
    assert loser.json()["error"] == "telegram_already_linked"
    assert await _count_by_telegram(db_session, tg_id) == 1


# ---------------------------------------------------------------------------
# Threat 14 -- the link token
# ---------------------------------------------------------------------------


async def test_threat14_token_is_single_use_under_concurrency(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two confirms with the same token and the right code at once: one
    wins, the other is told the link is dead."""
    email = _email()
    tok = await _start(client)
    assert (await link_telegram_email(client, tok, email)).status_code == 200
    code = await read_telegram_link_code(tok)

    first, second = await asyncio.gather(
        link_telegram_confirm(client, tok, code),
        link_telegram_confirm(client, tok, code),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 400]
    loser = second if first.status_code == 200 else first
    assert loser.json()["error"] == "link_token_invalid"


async def test_claim_session_of_an_unproven_holder_does_not_survive(
    client: AsyncClient,
) -> None:
    """Every other session of a claimed row is ended after the commit; the
    prover's new one stays."""
    email = _email()
    attacker = await register_user(client, email=email, password="AttackerPass1!")
    _t, _c, resp = await _flow(client, email)
    assert resp.status_code == 200, resp.text
    assert not await _session_alive(client, attacker["session_token"])
    assert await _session_alive(client, resp.json()["session_token"])



async def test_threat14_token_is_single_use(client: AsyncClient) -> None:
    tok, code, first = await _flow(client, _email())
    assert first.status_code == 200

    second = await link_telegram_confirm(client, tok, code)
    assert second.status_code == 400
    assert second.json()["error"] == "link_token_invalid"
    assert await get_redis().get(f"telegram_link:{tok}") is None


async def test_threat14_unknown_token_and_no_code_yet(client: AsyncClient) -> None:
    resp = await link_telegram_confirm(client, "no-such-token", "123456")
    assert resp.status_code == 400
    assert resp.json()["error"] == "link_token_invalid"

    resp = await link_telegram_email(client, "no-such-token", _email())
    assert resp.status_code == 400
    assert resp.json()["error"] == "link_token_invalid"

    tok = await _start(client)
    resp = await link_telegram_confirm(client, tok, "123456")
    assert resp.status_code == 400
    assert resp.json()["error"] == "link_code_not_requested"


# ---------------------------------------------------------------------------
# Threat 16 -- the two letters name the Telegram account
# ---------------------------------------------------------------------------


async def test_threat16_code_for_an_existing_row_names_the_telegram_account(
    client: AsyncClient, recorder: Recorder
) -> None:
    email, _pw, body = await _verified_web_user(client)
    recorder.payloads.clear()

    tok = await _start(client, username="attacker_tg", first_name="Mallory")
    assert (await link_telegram_email(client, tok, email)).status_code == 200
    code = await read_telegram_link_code(tok)

    letters = recorder.of_type("auth.telegram_link_code")
    assert len(letters) == 1
    letter = letters[0]
    assert letter["target_type"] == "user"
    assert letter["target_value"] == body["user"]["id"]
    # The letter itself is in the request (H43, app/letters).
    text = letter["email"]["text"]
    assert "@attacker_tg" in text
    assert code in text
    assert "10 minutes" in text or "10 минут" in text
    assert "@attacker_tg" in letter["email"]["html"]
    every_part = [letter["title"], letter["body"], *letter["email"].values()]
    assert all("Mallory" not in part for part in every_part)  # never the free-text name
    assert not recorder.of_type("auth.verification_code")


async def test_threat16_code_for_a_new_person_reuses_the_existing_letter(
    client: AsyncClient, recorder: Recorder
) -> None:
    tok = await _start(client)
    assert (await link_telegram_email(client, tok, _email())).status_code == 200
    code = await read_telegram_link_code(tok)

    letters = recorder.of_type("auth.verification_code")
    assert len(letters) == 1
    assert code in letters[0]["email"]["text"]
    assert not recorder.of_type("auth.telegram_link_code")


async def test_threat16_a_notice_follows_every_link(
    client: AsyncClient, recorder: Recorder
) -> None:
    email, _pw, body = await _verified_web_user(client)
    _t, _c, resp = await _flow(client, email, username="the_owner")
    assert resp.status_code == 200, resp.text

    notices = recorder.of_type("auth.telegram_linked")
    assert len(notices) == 1
    assert notices[0]["target_value"] == body["user"]["id"]
    assert "@the_owner" in notices[0]["email"]["text"]
    assert "expiry_at" not in notices[0] or notices[0]["expiry_at"] is None


async def test_threat16_no_notice_when_the_link_is_refused(
    client: AsyncClient, recorder: Recorder
) -> None:
    email, _pw, _b = await _verified_web_user(client)
    _t, _c, first = await _flow(client, email)
    assert first.status_code == 200
    recorder.payloads.clear()

    _t, _c, refused = await _flow(client, email)
    assert refused.status_code == 403
    assert not recorder.of_type("auth.telegram_linked")


# ---------------------------------------------------------------------------
# Consent record: the server signs both documents at confirm
# ---------------------------------------------------------------------------


async def test_consent_is_signed_by_the_server_at_confirm(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    doc_ids = await _ensure_consent_documents(db_session)
    email = _email()

    _t, _c, resp = await _flow(
        client, email, headers={"User-Agent": "pytest-link-agent"}
    )
    assert resp.status_code == 200, resp.text
    user_id = uuid.UUID(resp.json()["user"]["id"])

    signings = (
        (
            await db_session.execute(
                select(DocumentSigning)
                .where(DocumentSigning.user_id == user_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    signed = {s.document_id for s in signings}
    assert set(doc_ids.values()) <= signed
    for signing in signings:
        assert signing.ip_address  # the request's address
        assert signing.user_agent == "pytest-link-agent"
        assert signing.signed_at is not None


async def test_consent_must_be_given_at_the_email_step(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email = _email()
    tok = await _start(client)
    resp = await link_telegram_email(client, tok, email, consent_given=False)
    assert resp.status_code == 400
    assert resp.json()["error"] == "consent_required"
    # Nothing was made and nothing was sent.
    assert await _count_by_email(db_session, email) == 0
    record = json.loads(await get_redis().get(f"telegram_link:{tok}"))
    assert record["code"] is None


async def test_consent_already_signed_on_the_web_is_not_added_twice(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    doc_ids = await _ensure_consent_documents(db_session)
    email, _pw, body = await _verified_web_user(client)
    user_id = uuid.UUID(body["user"]["id"])
    db_session.add(
        DocumentSigning(
            user_id=user_id,
            document_id=doc_ids["cabinet_terms"],
            ip_address="203.0.113.7",
            user_agent="web-browser",
        )
    )
    await db_session.commit()

    _t, _c, resp = await _flow(client, email)
    assert resp.status_code == 200, resp.text

    rows = (
        (
            await db_session.execute(
                select(DocumentSigning)
                .where(DocumentSigning.user_id == user_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    terms = [r for r in rows if r.document_id == doc_ids["cabinet_terms"]]
    assert len(terms) == 1
    assert terms[0].ip_address == "203.0.113.7"  # the web signing stands
    assert {r.document_id for r in rows} >= set(doc_ids.values())


# ---------------------------------------------------------------------------
# Rows made by the e-mail step (S5) and the referral of the prover
# ---------------------------------------------------------------------------


async def test_s5_row_has_no_password_telegram_or_referrer_until_the_proof(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent, _tok, link = await create_agent_with_link(client, db_session)
    platform_id = await get_platform_user_id(db_session)
    email = _email()

    tg_id = _tg()
    tok = await _start(client, tg_id, referral_code=link.code)
    assert (
        await link_telegram_email(client, tok, email, referral_code=link.code)
    ).status_code == 200

    row = await _load(db_session, email)
    assert row.email_verified is False
    assert "password_hash" not in row.credentials["email"]
    assert "telegram" not in row.credentials
    assert row.referred_by == platform_id
    assert row.referred_by_link_id is None
    assert await _count_by_telegram(db_session, tg_id) == 0

    code = await read_telegram_link_code(tok)
    resp = await link_telegram_confirm(client, tok, code)
    assert resp.status_code == 200, resp.text

    row = await _load(db_session, email)
    assert row.email_verified is True
    assert row.credentials["telegram"]["id"] == tg_id
    assert row.referred_by == agent.id
    assert row.referred_by_link_id == link.id


async def test_referrer_of_a_claimed_row_is_the_provers_not_the_requesters(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent, _tok, link = await create_agent_with_link(client, db_session)
    platform_id = await get_platform_user_id(db_session)
    email = _email()
    await register_user(client, email=email, referral_code=link.code)
    assert (await _load(db_session, email)).referred_by == agent.id

    _t, _c, resp = await _flow(client, email)  # the prover brings no code
    assert resp.status_code == 200, resp.text

    row = await _load(db_session, email)
    assert row.referred_by == platform_id
    assert row.referred_by_link_id is None


async def test_referrer_of_a_verified_row_is_kept(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    agent, _tok, link = await create_agent_with_link(client, db_session)
    _other, _t2, other_link = await create_agent_with_link(client, db_session)
    email = _email()
    body = await register_user(client, email=email, referral_code=link.code)
    await confirm_email(body["user"]["id"])

    _t, _c, resp = await _flow(client, email, referral_code=other_link.code)
    assert resp.status_code == 200, resp.text

    row = await _load(db_session, email)
    assert row.referred_by == agent.id
    assert row.referred_by_link_id == link.id


# ---------------------------------------------------------------------------
# comms: the recipient is synced after the Telegram id is written
# ---------------------------------------------------------------------------


async def test_recipient_is_synced_after_the_telegram_id_is_written(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, Any]] = []

    async def fake_sync(session: Any, user: User) -> bool:
        calls.append(
            (str(user.id), ((user.credentials or {}).get("telegram") or {}).get("id"))
        )
        return True

    monkeypatch.setattr(auth_service, "sync_recipient", fake_sync)

    tg_id = _tg()
    _t, _c, resp = await _flow(client, _email(), telegram_id=tg_id)
    assert resp.status_code == 200, resp.text
    user_id = resp.json()["user"]["id"]

    mine = [c for c in calls if c[0] == user_id]
    assert mine[0][1] is None  # the e-mail-only row, at creation
    assert mine[-1][1] == tg_id  # and again with the Telegram id in it
