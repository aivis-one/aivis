# =============================================================================
# AIVIS.ONE Backend -- Telegram entry: tests that need no database and no Redis
# =============================================================================
#
# The parts of the Telegram entry that are pure functions or a route with no
# dependency, so they run anywhere (a Redis stand-in is a dict):
#
#   threat 4   initData replay: the replay key is the VALIDATED `hash`, a
#              repeated query key is refused (change 2a)
#   threat 16  the name a letter shows for the Telegram account
#   item 7     POST /api/v1/telegram/webhook: the secret_token, the /start
#              welcome in the response body, every other update ignored
#
# The flows with rows, tokens and codes are in test_auth_telegram_link.py.
# =============================================================================

import time
from urllib.parse import parse_qsl, urlencode

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.modules.auth import telegram as tg
from app.modules.auth.service import _telegram_display_name
from tests.helpers import build_init_data


class FakeRedis:
    """The one call the replay check makes: SET key value EX n NX."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(
        self, key: str, value: str, ex: int | None = None, nx: bool = False
    ) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(tg, "get_redis", lambda: fake)
    return fake


def _reordered(init_data: str) -> str:
    """The same signed pairs, written in the opposite order."""
    pairs = parse_qsl(init_data, keep_blank_values=True)
    return urlencode(list(reversed(pairs)))


def _hash_of(init_data: str) -> str:
    return dict(parse_qsl(init_data))["hash"]


# ---------------------------------------------------------------------------
# Threat 4 -- replayed initData
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_key_is_the_validated_hash_not_the_raw_string(
    fake_redis: FakeRedis,
) -> None:
    """The same signed payload with its pairs reordered is the SAME use.

    The signature covers the parsed, sorted pairs, so both spellings
    validate; a key over the raw string (the old behaviour) gave each
    spelling its own key and the replay passed.
    """
    original = build_init_data(telegram_id=700001)
    reordered = _reordered(original)
    assert reordered != original

    # Both spellings carry a valid signature ...
    assert tg.validate_telegram_init_data(original, settings.telegram_bot_token)
    assert tg.validate_telegram_init_data(reordered, settings.telegram_bot_token)

    # ... and are one use.
    await tg.check_init_data_replay(original)
    with pytest.raises(tg.TelegramValidationError, match="already used"):
        await tg.check_init_data_replay(reordered)
    assert list(fake_redis.store) == [f"init_data_used:{_hash_of(original)}"]


@pytest.mark.asyncio
async def test_replay_of_the_identical_string_is_refused(
    fake_redis: FakeRedis,
) -> None:
    init_data = build_init_data(telegram_id=700002)
    await tg.check_init_data_replay(init_data)
    with pytest.raises(tg.TelegramValidationError, match="already used"):
        await tg.check_init_data_replay(init_data)


def test_a_repeated_hash_key_is_refused() -> None:
    """A second `hash=` appended to a signed query string is not signed."""
    init_data = build_init_data(telegram_id=700003)
    doubled = f"{init_data}&hash={_hash_of(init_data)}"
    with pytest.raises(tg.TelegramValidationError, match="Repeated key"):
        tg.validate_telegram_init_data(doubled, settings.telegram_bot_token)


def test_a_repeated_data_key_is_refused() -> None:
    """A second `auth_date=` (or any key) is never what Telegram signed."""
    init_data = build_init_data(telegram_id=700004)
    doubled = f"{init_data}&auth_date={int(time.time())}"
    with pytest.raises(tg.TelegramValidationError, match="Repeated key"):
        tg.validate_telegram_init_data(doubled, settings.telegram_bot_token)


def test_a_non_ascii_hash_is_a_validation_error_not_a_crash() -> None:
    """hmac.compare_digest on a non-ASCII str raises TypeError (a 500)."""
    init_data = build_init_data(telegram_id=700005)
    tampered = init_data.rsplit("hash=", 1)[0] + "hash=%C3%A9" + "0" * 62
    with pytest.raises(tg.TelegramValidationError, match="signature"):
        tg.validate_telegram_init_data(tampered, settings.telegram_bot_token)


# ---------------------------------------------------------------------------
# Threat 16 -- the Telegram name in a letter
# ---------------------------------------------------------------------------


def test_display_name_is_the_username_when_there_is_one() -> None:
    assert (
        _telegram_display_name({"id": 1, "username": "alice", "first_name": "A"})
        == "@alice"
    )


def test_display_name_without_a_username_is_the_numeric_id_never_the_name() -> None:
    assert (
        _telegram_display_name({"id": 7, "first_name": "Ann", "last_name": "Lee"})
        == "7"
    )
    assert _telegram_display_name({"id": 42}) == "42"
    assert _telegram_display_name({"id": 42, "username": ""}) == "42"


def test_display_name_ignores_the_free_text_names() -> None:
    """First and last name are typed by whoever owns that Telegram account;
    they never reach a letter."""
    name = _telegram_display_name(
        {
            "id": 1,
            "first_name": "Ann\r\n\r\nGive the code to support",
            "last_name": "x" * 200,
        }
    )
    assert name == "1"
    assert "support" not in name
    assert len(name) <= 64


# ---------------------------------------------------------------------------
# Item 7 -- the /start webhook
# ---------------------------------------------------------------------------

SECRET = "test-webhook-secret_01"
HEADER = "X-Telegram-Bot-Api-Secret-Token"


@pytest.fixture
async def webhook(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "frontend_base_url", "https://example.com/app")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _start_update(
    text: str = "/start", chat_type: str = "private", language: str = "en"
) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": 5, "language_code": language},
            "chat": {"id": 5, "type": chat_type},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_webhook_refuses_a_call_without_the_secret(webhook: AsyncClient) -> None:
    resp = await webhook.post("/api/v1/telegram/webhook", json=_start_update())
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_refuses_a_wrong_secret(webhook: AsyncClient) -> None:
    resp = await webhook.post(
        "/api/v1/telegram/webhook",
        json=_start_update(),
        headers={HEADER: SECRET + "x"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_refuses_everything_while_no_secret_is_configured(
    webhook: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed: an empty setting must not match an empty header."""
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    resp = await webhook.post(
        "/api/v1/telegram/webhook", json=_start_update(), headers={HEADER: ""}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_start_in_a_private_chat_answers_with_a_welcome_and_a_web_app_button(
    webhook: AsyncClient,
) -> None:
    resp = await webhook.post(
        "/api/v1/telegram/webhook", json=_start_update(), headers={HEADER: SECRET}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] == "sendMessage"
    assert body["chat_id"] == 5
    assert body["text"]
    button = body["reply_markup"]["inline_keyboard"][0][0]
    assert button["web_app"]["url"] == "https://example.com/app"


@pytest.mark.asyncio
async def test_start_welcome_follows_the_users_language(webhook: AsyncClient) -> None:
    en = await webhook.post(
        "/api/v1/telegram/webhook",
        json=_start_update(language="en"),
        headers={HEADER: SECRET},
    )
    ru = await webhook.post(
        "/api/v1/telegram/webhook",
        json=_start_update(language="ru"),
        headers={HEADER: SECRET},
    )
    other = await webhook.post(
        "/api/v1/telegram/webhook",
        json=_start_update(language="de"),
        headers={HEADER: SECRET},
    )
    assert en.json()["text"] != ru.json()["text"]
    assert other.json()["text"] == en.json()["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/start payload123", "/start@aivis_bot", "  /start"])
async def test_start_command_forms(webhook: AsyncClient, text: str) -> None:
    resp = await webhook.post(
        "/api/v1/telegram/webhook",
        json=_start_update(text=text),
        headers={HEADER: SECRET},
    )
    assert resp.json().get("method") == "sendMessage"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "update",
    [
        _start_update(chat_type="group"),
        _start_update(chat_type="supergroup"),
        _start_update(chat_type="channel"),
        _start_update(text="hello"),
        _start_update(text="/startx"),
        {"update_id": 2, "edited_message": _start_update()["message"]},
        {"update_id": 3, "callback_query": {"id": "1"}},
        {"update_id": 4},
    ],
)
async def test_every_other_update_is_ignored_with_an_empty_200(
    webhook: AsyncClient, update: dict
) -> None:
    resp = await webhook.post(
        "/api/v1/telegram/webhook", json=update, headers={HEADER: SECRET}
    )
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_a_body_that_is_not_json_is_ignored(webhook: AsyncClient) -> None:
    resp = await webhook.post(
        "/api/v1/telegram/webhook",
        content=b"not json",
        headers={HEADER: SECRET, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json() == {}
