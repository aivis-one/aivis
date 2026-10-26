# =============================================================================
# AIVIS.ONE Backend -- Tests: the website sign-in through Telegram (H45)
# =============================================================================
#
# Telegram is not reached: telegram_oidc._client is replaced by an httpx mock
# transport that answers the token exchange with an id_token this file signs
# with its own RSA key, and the key set with that key's public half. Every
# claim, signature and refusal is therefore built here, by hand, on purpose.
#
# AXES: repeat -- a state is taken once, a second return is refused; emptiness
# -- no keys (the sign-in is off), no state, a mark of another browser;
# shortage -- an expired, foreign-audience, foreign-issuer, unsigned-by-us
# token, a token without iat, an id that is not a Telegram id.
# =============================================================================

import base64
import hashlib
import json
import secrets
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.core.database import get_session_factory
from app.core.redis import get_redis
from app.modules.auth import telegram_oidc, web_login
from app.modules.users.models import User
from tests.helpers import (
    build_init_data,
    login_telegram,
    read_telegram_link_code,
    register_user,
    telegram_entry,
)

CLIENT_ID = "8123456789"
CLIENT_SECRET = "test-client-secret-never-logged"
KID = "test-key-1"


def _tg() -> int:
    """A fresh Telegram id above int32, never reused."""
    return 7_000_000_000 + secrets.randbelow(1_000_000_000)


def _mark() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Telegram, faked: keys, tokens, the two HTTP calls
# ---------------------------------------------------------------------------


class FakeTelegram:
    """Signs id_tokens and answers the token and key requests."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        self.jwks = {"keys": [{**public, "kid": KID, "alg": "RS256", "use": "sig"}]}
        self.claims: dict[str, Any] = {}
        self.token_status = 200
        self.requests: list[httpx.Request] = []
        self.events: list[str] | None = None

    def sign(
        self,
        claims: dict[str, Any],
        *,
        key: Any = None,
        kid: str = KID,
        alg: str = "RS256",
    ) -> str:
        signer = key if key is not None else self.key
        return jwt.encode(claims, signer, algorithm=alg, headers={"kid": kid})

    def good_claims(self, telegram_id: int, **extra: Any) -> dict[str, Any]:
        now = int(time.time())
        return {
            "iss": telegram_oidc.ISSUER,
            "aud": CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "sub": "opaque",
            "id": telegram_id,
            **extra,
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.events is not None:
            self.events.append("http")
        if str(request.url) == telegram_oidc.TOKEN_URL:
            if self.token_status != 200:
                return httpx.Response(
                    self.token_status, json={"error": "invalid_grant"}
                )
            return httpx.Response(200, json={"id_token": self.sign(self.claims)})
        if str(request.url) == telegram_oidc.JWKS_URL:
            return httpx.Response(200, json=self.jwks)
        return httpx.Response(404)


@pytest.fixture
def telegram(monkeypatch: pytest.MonkeyPatch) -> FakeTelegram:
    """The sign-in switched on, Telegram faked, this file's IP limit cleared."""
    fake = FakeTelegram()
    monkeypatch.setattr(settings, "telegram_login_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "telegram_login_client_secret", CLIENT_SECRET)
    monkeypatch.setattr(
        telegram_oidc,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
    )
    return fake


@pytest.fixture(autouse=True)
async def _clear_web_ip_limit() -> None:
    await get_redis().delete("telegram_web_ip:127.0.0.1")


async def _start(
    client: AsyncClient,
    mark: str,
    *,
    referral_code: str | None = None,
    language: str | None = None,
) -> tuple[str, str]:
    body: dict[str, Any] = {"mark": mark}
    if referral_code is not None:
        body["referral_code"] = referral_code
    if language is not None:
        body["language"] = language
    resp = await client.post("/api/v1/auth/telegram/web/start", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["url"], resp.json()["state"]


async def _complete(client: AsyncClient, state: str, mark: str, code: str = "c0de"):
    return await client.post(
        "/api/v1/auth/telegram/web/complete",
        json={"code": code, "state": state, "mark": mark},
    )


async def _sign_in(
    client: AsyncClient, telegram: FakeTelegram, telegram_id: int, **claims: Any
):
    """A whole website sign-in of `telegram_id`; returns the complete response."""
    telegram.claims = telegram.good_claims(telegram_id, **claims)
    mark = _mark()
    _url, state = await _start(client, mark)
    return await _complete(client, state, mark)


async def _row_by_telegram(telegram_id: int) -> User | None:
    async with get_session_factory()() as session:
        rows = (
            (
                await session.execute(
                    select(User).where(
                        User.credentials["telegram"]["id"].astext == str(telegram_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) <= 1
        return rows[0] if rows else None


async def _user_count() -> int:
    async with get_session_factory()() as session:
        return (
            await session.execute(select(func.count()).select_from(User))
        ).scalar_one()


async def _write_row(user_id: str, **changes: Any) -> None:
    async with get_session_factory()() as session:
        user = (
            await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
        ).scalar_one()
        for key, value in changes.items():
            if key == "credentials":
                user.set_jsonb("credentials", value)
            else:
                setattr(user, key, value)
        await session.commit()


# ---------------------------------------------------------------------------
# 1. The keys: both or neither
# ---------------------------------------------------------------------------


def test_neither_key_starts_and_the_sign_in_is_off() -> None:
    s = Settings(
        app_env="development",
        telegram_login_client_id="",
        telegram_login_client_secret="",
    )
    assert s.telegram_login_client_id == ""
    assert s.telegram_login_client_secret == ""


def test_both_keys_start() -> None:
    s = Settings(
        app_env="development",
        telegram_login_client_id=CLIENT_ID,
        telegram_login_client_secret=CLIENT_SECRET,
    )
    assert s.telegram_login_client_id == CLIENT_ID


@pytest.mark.parametrize(
    ("client_id", "secret", "missing"),
    [
        (CLIENT_ID, "", "TELEGRAM_LOGIN_CLIENT_SECRET"),
        ("", CLIENT_SECRET, "TELEGRAM_LOGIN_CLIENT_ID"),
        (CLIENT_ID, "   ", "TELEGRAM_LOGIN_CLIENT_SECRET"),
    ],
    ids=["no-secret", "no-id", "blank-secret"],
)
def test_one_key_refuses_the_start_and_names_the_other(
    client_id: str, secret: str, missing: str
) -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="development",
            telegram_login_client_id=client_id,
            telegram_login_client_secret=secret,
        )
    message = str(exc.value)
    assert missing in message
    assert CLIENT_SECRET not in message


async def test_availability_follows_the_keys(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "telegram_login_client_id", "")
    monkeypatch.setattr(settings, "telegram_login_client_secret", "")
    off = await client.get("/api/v1/auth/telegram/web")
    assert off.status_code == 200
    assert off.json() == {"available": False}
    start = await client.post("/api/v1/auth/telegram/web/start", json={"mark": _mark()})
    assert start.status_code == 404
    assert start.json()["error"] == "login_not_configured"

    monkeypatch.setattr(settings, "telegram_login_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "telegram_login_client_secret", CLIENT_SECRET)
    on = await client.get("/api/v1/auth/telegram/web")
    assert on.json() == {"available": True}


# ---------------------------------------------------------------------------
# 2. start and the id_token
# ---------------------------------------------------------------------------


async def test_start_sends_the_browser_to_telegram_with_pkce_and_our_return(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    url, state = await _start(client, _mark())
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == telegram_oidc.AUTHORIZE_URL
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert q["client_id"] == CLIENT_ID
    assert (
        q["redirect_uri"]
        == settings.frontend_base_url.rstrip("/") + web_login.RETURN_PATH
    )
    assert q["response_type"] == "code"
    assert q["scope"] == "openid profile"
    assert q["state"] == state
    assert q["code_challenge_method"] == "S256"
    assert len(q["code_challenge"]) == 43


@pytest.fixture
def keys_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "telegram_login_client_id", CLIENT_ID)


def test_a_good_token_proves_the_user(keys_on: None) -> None:
    fake = FakeTelegram()
    user = telegram_oidc.verify_id_token(
        fake.sign(
            fake.good_claims(
                123456789,
                given_name="Ann",
                family_name="Lee",
                preferred_username="ann",
                picture="https://cdn.example.com/userpic/ann.jpg",
            )
        ),
        fake.jwks,
    )
    assert user == telegram_oidc.TelegramUser(
        telegram_id=123456789,
        first_name="Ann",
        last_name="Lee",
        username="ann",
        photo_url="https://cdn.example.com/userpic/ann.jpg",
    )


def _refused(fake: FakeTelegram, token: str) -> str:
    with pytest.raises(telegram_oidc.TelegramLoginError) as exc:
        telegram_oidc.verify_id_token(token, fake.jwks)
    return exc.value.reason


def test_every_bad_token_is_refused(keys_on: None) -> None:
    fake = FakeTelegram()
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    good = fake.good_claims(42)
    now = int(time.time())

    assert _refused(fake, fake.sign(good, key=other)) == "bad_id_token"
    assert _refused(fake, fake.sign({**good, "aud": "999"})) == "bad_id_token"
    assert (
        _refused(fake, fake.sign({**good, "iss": "https://evil.example"}))
        == "bad_id_token"
    )
    assert (
        _refused(fake, fake.sign({**good, "exp": now - 120, "iat": now - 600}))
        == "bad_id_token"
    )
    no_iat = {k: v for k, v in good.items() if k != "iat"}
    assert _refused(fake, fake.sign(no_iat)) == "bad_id_token"
    assert _refused(fake, fake.sign(good, kid="unknown")) == "unknown_key"
    hs = jwt.encode(
        good,
        "shared-secret-of-at-least-32-bytes!!",
        algorithm="HS256",
        headers={"kid": KID},
    )
    assert _refused(fake, hs) == "bad_algorithm"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (42, 42),
        ("42", 42),
        ("0042", 42),
        (True, None),
        (0, None),
        ("-5", None),
        ("4 2", None),
        ("٤٢", None),
        ("9" * 20, None),
        (None, None),
        (4.0, None),
    ],
    ids=[
        "int",
        "digits",
        "zeros",
        "bool",
        "zero",
        "sign",
        "space",
        "arabic",
        "too-big",
        "absent",
        "float",
    ],
)
def test_the_telegram_id_claim_in_every_form(
    keys_on: None, value: object, expected: int | None
) -> None:
    fake = FakeTelegram()
    claims = fake.good_claims(1)
    if value is None:
        claims.pop("id")
    else:
        claims["id"] = value
    if expected is None:
        assert _refused(fake, fake.sign(claims)) == "no_telegram_id"
    else:
        assert (
            telegram_oidc.verify_id_token(fake.sign(claims), fake.jwks).telegram_id
            == expected
        )


def test_the_translator_gives_the_mini_app_shape() -> None:
    user = telegram_oidc.TelegramUser(
        telegram_id=77, first_name="A", last_name=None, username="u", photo_url=None
    )
    shaped = telegram_oidc.as_init_data_user(user)
    assert shaped == {
        "id": 77,
        "first_name": "A",
        "last_name": None,
        "username": "u",
        "photo_url": None,
        "language_code": None,
    }
    assert type(shaped["id"]) is int


# ---------------------------------------------------------------------------
# 3. complete: state, mark, Telegram's refusal
# ---------------------------------------------------------------------------


async def test_a_state_is_taken_once(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    telegram.claims = telegram.good_claims(_tg())
    mark = _mark()
    _url, state = await _start(client, mark)
    first = await _complete(client, state, mark)
    assert first.status_code == 200, first.text
    again = await _complete(client, state, mark)
    assert again.status_code == 400
    assert again.json()["error"] == "login_expired"


async def test_an_unknown_state_is_refused(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    resp = await _complete(client, secrets.token_urlsafe(32), _mark())
    assert resp.status_code == 400
    assert resp.json()["error"] == "login_expired"
    assert telegram.requests == []


async def test_a_return_in_another_browser_never_reaches_telegram(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    telegram.claims = telegram.good_claims(_tg())
    _url, state = await _start(client, _mark())
    resp = await _complete(client, state, _mark())
    assert resp.status_code == 400
    assert resp.json()["error"] == "login_foreign"
    assert telegram.requests == []


async def test_telegram_refusing_the_code_is_telegram_failed(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    telegram.token_status = 400
    mark = _mark()
    _url, state = await _start(client, mark)
    resp = await _complete(client, state, mark)
    assert resp.status_code == 400
    assert resp.json()["error"] == "telegram_failed"


async def test_the_code_is_exchanged_with_the_stored_return_and_verifier(
    client: AsyncClient, telegram: FakeTelegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    telegram.claims = telegram.good_claims(_tg())
    mark = _mark()
    url, state = await _start(client, mark)
    challenge = parse_qs(urlsplit(url).query)["code_challenge"][0]
    stored_return = web_login.return_url()
    # The site's address changes between start and return: the exchange must
    # still use the address the sign-in started with.
    monkeypatch.setattr(settings, "frontend_base_url", "https://elsewhere.example")
    resp = await _complete(client, state, mark, code="the-code")
    assert resp.status_code == 200, resp.text

    token_request = telegram.requests[0]
    form = {k: v[0] for k, v in parse_qs(token_request.content.decode()).items()}
    assert form["redirect_uri"] == stored_return
    assert form["code"] == "the-code"
    verifier_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(form["code_verifier"].encode()).digest()
        )
        .decode()
        .rstrip("=")
    )
    assert verifier_challenge == challenge
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    assert token_request.headers["authorization"] == f"Basic {basic}"


async def test_telegram_is_asked_before_the_first_database_statement(
    client: AsyncClient, telegram: FakeTelegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    telegram.events = events
    real_execute = AsyncSession.execute

    async def recording_execute(self: AsyncSession, *args: Any, **kwargs: Any) -> Any:
        events.append("db")
        return await real_execute(self, *args, **kwargs)

    telegram.claims = telegram.good_claims(_tg())
    mark = _mark()
    _url, state = await _start(client, mark)
    monkeypatch.setattr(AsyncSession, "execute", recording_execute)
    resp = await _complete(client, state, mark)
    assert resp.status_code == 200, resp.text
    assert events[:2] == ["http", "http"]
    assert "db" in events


# ---------------------------------------------------------------------------
# 4. The shared path: known, two-factor, unknown, refused
# ---------------------------------------------------------------------------


async def test_a_known_telegram_gets_a_session(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    tg_id = _tg()
    mini = await login_telegram(client, telegram_id=tg_id)
    resp = await _sign_in(client, telegram, tg_id)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session_token"]
    assert body["user"]["id"] == mini["user"]["id"]
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {body['session_token']}"}
    )
    assert me.status_code == 200


async def test_two_factor_asks_for_the_second_code(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    tg_id = _tg()
    mini = await login_telegram(client, telegram_id=tg_id)
    row = await _row_by_telegram(tg_id)
    assert row is not None
    await _write_row(
        mini["user"]["id"], credentials={**row.credentials, "totp": {"enabled": True}}
    )
    resp = await _sign_in(client, telegram, tg_id)
    assert resp.status_code == 200
    assert resp.json()["mfa_required"] is True
    assert resp.json()["mfa_token"]
    assert resp.json()["session_token"] is None


async def test_an_unknown_telegram_creates_nothing_and_gets_a_link_token(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    tg_id = _tg()
    before = await _user_count()
    telegram.claims = telegram.good_claims(tg_id, given_name="New")
    mark = _mark()
    _url, state = await _start(client, mark, referral_code="REF123", language="ru")
    resp = await _complete(client, state, mark)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["link_required"] is True and body["link_token"]
    assert body["session_token"] is None
    assert await _user_count() == before
    assert await _row_by_telegram(tg_id) is None

    record = json.loads(await get_redis().get(f"telegram_link:{body['link_token']}"))
    assert record["referral_code"] == "REF123"
    assert record["language"] == "ru"
    assert record["telegram"]["id"] == tg_id
    assert record["telegram"]["language_code"] is None


async def test_without_a_language_the_link_token_is_english(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    resp = await _sign_in(client, telegram, _tg())
    record = json.loads(
        await get_redis().get(f"telegram_link:{resp.json()['link_token']}")
    )
    assert record["language"] == "en"
    assert record["referral_code"] is None


@pytest.mark.parametrize(
    ("changes", "status", "error"),
    [
        ({"is_active": False}, 403, "account_blocked"),
        ({"is_active": False, "self": True}, 403, "account_self_deactivated"),
        ({"role": "platform"}, 401, None),
    ],
    ids=["blocked", "self-deactivated", "platform"],
)
async def test_refused_accounts_are_refused_as_in_the_mini_app(
    client: AsyncClient,
    telegram: FakeTelegram,
    changes: dict,
    status: int,
    error: str | None,
) -> None:
    tg_id = _tg()
    mini = await login_telegram(client, telegram_id=tg_id)
    row = await _row_by_telegram(tg_id)
    assert row is not None
    write: dict[str, Any] = {k: v for k, v in changes.items() if k != "self"}
    if changes.get("self"):
        write["credentials"] = {
            **row.credentials,
            "account": {"deactivated_by": "self"},
        }
    await _write_row(mini["user"]["id"], **write)
    try:
        web = await _sign_in(client, telegram, tg_id)
        app = await client.post(
            "/api/v1/auth/telegram",
            json={"init_data": build_init_data(tg_id)},
        )
    finally:
        # The suite has no per-test rollback; a second platform row would
        # break get_platform_user_id for every test after this one.
        await _write_row(mini["user"]["id"], role="investor", is_active=True)
    assert web.status_code == status == app.status_code
    if error is not None:
        assert web.json()["error"] == error == app.json()["error"]
    assert "session_token" not in web.text or web.json().get("session_token") is None


async def test_the_shared_path_rate_limits_per_telegram_id(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    """The Mini App's per-Telegram-id limit (auth_rate:{id}) holds the
    website door too. Pair: with the counter clear the same sign-in passes."""
    tg_id = _tg()
    await login_telegram(client, telegram_id=tg_id)
    await get_redis().set(f"auth_rate:{tg_id}", 10_000, ex=60)
    limited = await _sign_in(client, telegram, tg_id)
    assert limited.status_code == 429

    await get_redis().delete(f"auth_rate:{tg_id}")
    passed = await _sign_in(client, telegram, tg_id)
    assert passed.status_code == 200


# ---------------------------------------------------------------------------
# 5. One person, one record -- condition 2 of the owner
# ---------------------------------------------------------------------------


async def test_the_same_person_writes_the_same_record_through_either_door(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    tg_id = _tg()
    mini = await login_telegram(client, telegram_id=tg_id)
    by_app = await telegram_entry(
        client,
        telegram_id=tg_id,
        first_name="Ann",
        last_name="Lee",
        username="annlee",
        language="ru",
    )
    assert by_app["session_token"]
    after_app = (await _row_by_telegram(tg_id)).credentials["telegram"]  # type: ignore[union-attr]

    resp = await _sign_in(
        client,
        telegram,
        tg_id,
        given_name="Ann",
        family_name="Lee",
        preferred_username="annlee",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["id"] == mini["user"]["id"]
    after_web = (await _row_by_telegram(tg_id)).credentials["telegram"]  # type: ignore[union-attr]

    assert after_web == after_app
    # The website carries no language and does not erase the Mini App's.
    assert after_web["language_code"] == "ru"
    assert type(after_web["id"]) is int


# ---------------------------------------------------------------------------
# 6. The password screen -- condition 3 of the owner, through the website
# ---------------------------------------------------------------------------


async def test_an_account_with_a_password_never_sees_the_screen_after_the_website(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    email = f"pw_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email, email_confirmed=True)
    tg_id = _tg()
    linked = await login_telegram(client, telegram_id=tg_id, email=email)
    assert linked["user"]["password_required"] is False

    resp = await _sign_in(client, telegram, tg_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["password_required"] is False


async def test_a_new_person_from_the_website_is_asked_for_a_password(
    client: AsyncClient, telegram: FakeTelegram
) -> None:
    resp = await _sign_in(client, telegram, _tg())
    token = resp.json()["link_token"]
    email = f"web_{uuid.uuid4().hex[:12]}@example.com"
    sent = await client.post(
        "/api/v1/auth/telegram/link/email",
        json={"link_token": token, "email": email, "consent_given": True},
    )
    assert sent.status_code == 200
    code = await read_telegram_link_code(token)
    done = await client.post(
        "/api/v1/auth/telegram/link/confirm", json={"link_token": token, "code": code}
    )
    assert done.status_code == 200, done.text
    assert done.json()["user"]["password_required"] is True


# ---------------------------------------------------------------------------
# 7. Secrets stay out of the log
# ---------------------------------------------------------------------------


async def test_no_secret_reaches_the_log(
    client: AsyncClient, telegram: FakeTelegram, capfd: pytest.CaptureFixture[str]
) -> None:
    """What the app prints -- structlog writes to stdout (core/logging.py) --
    over a foreign return, a good sign-in and a refused code. Read at the
    file-descriptor level, where a leaked secret would land. Pair: the
    refusals' own log lines are there, so the capture sees the log."""
    tg_id = _tg()
    telegram.claims = telegram.good_claims(tg_id)
    mark, foreign_mark = _mark(), _mark()
    capfd.readouterr()
    _url, state = await _start(client, mark)
    await _complete(client, state, foreign_mark, code="secret-code-1")
    _url2, state2 = await _start(client, mark)
    await _complete(client, state2, mark, code="secret-code-2")
    telegram.token_status = 400
    await get_redis().delete("telegram_web_ip:127.0.0.1")
    _url3, state3 = await _start(client, mark)
    await _complete(client, state3, mark, code="secret-code-3")
    out = capfd.readouterr()
    dump = out.out + out.err

    assert "telegram_web_foreign_return" in dump
    assert "telegram_login_token_refused" in dump
    id_token = telegram.sign(telegram.claims)
    for secret in (
        CLIENT_SECRET,
        mark,
        foreign_mark,
        state,
        state2,
        state3,
        "secret-code-1",
        "secret-code-2",
        "secret-code-3",
        id_token,
    ):
        assert secret not in dump
    verifiers = [
        parse_qs(r.content.decode()).get("code_verifier", [""])[0]
        for r in telegram.requests
        if str(r.url) == telegram_oidc.TOKEN_URL
    ]
    assert verifiers and all(v and v not in dump for v in verifiers)
