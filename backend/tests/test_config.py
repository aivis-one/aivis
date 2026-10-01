# =============================================================================
# AIVIS.ONE Backend -- Config Tests (R51)
# =============================================================================
#
# Tests cover:
#   1: Settings without APP_ENV (env scrubbed, no .env) -> refuses with
#      the fail-closed message (R51: pre-fix default was "development",
#      silently enabling the dev profile on any host missing its .env)
#   2: APP_ENV="" explicitly -> same refusal
#   3: APP_ENV=development -> dev defaults fill, is_dev True
#   4: APP_ENV with case/whitespace noise normalizes ("Development\\n"
#      -> "development"); any other value is production-grade and
#      enforces production requirements (no silent dev fallback)
#   5+: production requirements of H25 (P-108, P-116) -- empty,
#      placeholder, loopback and development values refused by name, all
#      at once; the good configuration and development unchanged as the
#      pair. See the section header further down.
#
# These construct Settings directly with _env_file=None and a scrubbed
# APP_ENV so the container's real environment never leaks in.
# =============================================================================

import pytest
from pydantic import ValidationError

from app.core.config import (
    _DEV_DATABASE_URL,
    _DEV_MINIO_CREDENTIAL,
    _DEV_MINIO_ENDPOINT,
    _DEV_SECRET_KEY,
    Settings,
)


def _scrub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove APP_ENV from the process environment."""
    monkeypatch.delenv("APP_ENV", raising=False)


def test_settings_refuse_without_app_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset APP_ENV -> fail-closed refusal with the R51 message."""
    _scrub(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "APP_ENV is required" in str(exc.value)


def test_settings_refuse_empty_app_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APP_ENV='' (set but empty) -> same refusal."""
    _scrub(monkeypatch)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, app_env="   ")
    assert "APP_ENV is required" in str(exc.value)


def test_settings_development_fills_dev_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """APP_ENV=development -> dev defaults, is_dev True."""
    _scrub(monkeypatch)
    s = Settings(_env_file=None, app_env="development")
    assert s.is_dev is True
    assert s.database_url  # dev fallback filled
    assert s.secret_key    # dev fallback filled


def test_settings_non_development_is_production_grade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any non-development value enforces production requirements --
    no silent dev fallback for typos like 'prod' or 'staging'."""
    _scrub(monkeypatch)

    # Normalization: case/whitespace noise still means development.
    s = Settings(_env_file=None, app_env="  Development\n")
    assert s.app_env == "development"
    assert s.is_dev is True

    # A typo'd / staging value is production-grade. The container's
    # real production env vars (CORS_ORIGINS, DATABASE_URL, ...) leak
    # into Settings and would satisfy the requirements, so the trigger
    # is forced deterministically: an explicit CORS wildcard kwarg
    # overrides the env, and non-development must reject it.
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, app_env="staging", cors_origins="*")
    assert "CORS_ORIGINS" in str(exc.value)


# =============================================================================
# Production requirements (H25: P-108 placeholders, P-116 dev values)
# =============================================================================
#
# Every constructor below passes EVERY guarded field explicitly. On the box
# this suite runs inside the app container, whose environment is a real
# production .env; a field left to the environment would make a test pass
# or fail by what that box happens to hold, not by what the test states.
#
# The three axes, per guarded input:
#   EMPTINESS -- "", whitespace only, the development default left in place
#   REPEAT    -- the placeholder in every case/whitespace form; several bad
#                values at once must each be named exactly once
#   SHORTAGE  -- a URL without scheme, without host, over http, with a
#                trailing slash, or naming a loopback host in any form
# and the pair every "refused" test needs: a good configuration starts and
# keeps each value exactly as given, non-empty.

_GOOD_REQUIRED = {
    "cors_origins": "https://app.aivis.one",
    "frontend_base_url": "https://app.aivis.one",
    "database_url": "postgresql+asyncpg://aivis:pw@postgres:5432/aivis",
    "redis_url": "redis://:pw@redis:6379/0",
    "secret_key": "k" * 64,
    "telegram_bot_token": "123456:ABC-real_token",
    "minio_endpoint": "http://minio:9000",
    "minio_access_key": "svcaccess0000001",
    "minio_secret_key": "svcsecret0000000000000000000001",
}

_NO_OPTIONAL_STACKS = {
    "comms_redis_url": "",
    "comms_api_url": "",
    "comms_service_token": "",
    "payments_api_url": "",
    "payments_service_token": "",
    "payments_webhook_secret": "",
}

_GOOD_OPTIONAL_STACKS = {
    "comms_redis_url": "redis://:pw@comms-redis:6379/0",
    "comms_api_url": "http://comms-app:8000",
    "comms_service_token": "comms-token",
    "payments_api_url": "http://payments-app:8000",
    "payments_service_token": "payments-token",
    "payments_webhook_secret": "payments-secret",
}

_ENV_NAME = {field: field.upper() for field in (
    list(_GOOD_REQUIRED) + list(_NO_OPTIONAL_STACKS)
)}

_PLACEHOLDER_FORMS = ["PLACEHOLDER", "placeholder", "TEST", "test", " Test "]


def _prod(**overrides: str) -> Settings:
    """A production Settings from a good baseline plus overrides."""
    values = {"app_env": "production", **_GOOD_REQUIRED, **_NO_OPTIONAL_STACKS}
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _refusal(**overrides: str) -> str:
    with pytest.raises(ValidationError) as exc:
        _prod(**overrides)
    return str(exc.value)


def test_production_accepts_a_good_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pair of every refusal below: a good production configuration
    starts, and every guarded value comes out exactly as given and
    non-empty -- with the optional stacks absent and with them present."""
    _scrub(monkeypatch)
    for optional in (_NO_OPTIONAL_STACKS, _GOOD_OPTIONAL_STACKS):
        s = _prod(**optional)
        assert s.is_dev is False
        for field, value in {**_GOOD_REQUIRED, **optional}.items():
            assert getattr(s, field) == value
        for field in _GOOD_REQUIRED:
            assert getattr(s, field)


@pytest.mark.parametrize("field", list(_GOOD_REQUIRED))
@pytest.mark.parametrize("bad", ["", "   ", *_PLACEHOLDER_FORMS])
def test_production_refuses_empty_or_placeholder_required(
    monkeypatch: pytest.MonkeyPatch, field: str, bad: str,
) -> None:
    """Every required setting: empty, blank and every placeholder form
    refuse the start and name the variable. PLACEHOLDER is the value the
    installer used to write on ENTER, and it passed the old check, which
    knew only "" and TEST."""
    _scrub(monkeypatch)
    message = _refusal(**{field: bad})
    assert _ENV_NAME[field] in message


@pytest.mark.parametrize("field", list(_NO_OPTIONAL_STACKS))
@pytest.mark.parametrize("bad", ["   ", *_PLACEHOLDER_FORMS])
def test_production_refuses_a_set_optional_value_that_is_not_a_value(
    monkeypatch: pytest.MonkeyPatch, field: str, bad: str,
) -> None:
    """Optional settings may be EMPTY (no such stack on this box -- the
    good-configuration test proves that starts), but a value that is set
    must be a value: blank or a placeholder is refused by name."""
    _scrub(monkeypatch)
    message = _refusal(**{**_GOOD_OPTIONAL_STACKS, field: bad})
    assert _ENV_NAME[field] in message


_URL_SHAPES = {
    "database_url": "postgresql+asyncpg://aivis:pw@{host}:5432/aivis",
    "redis_url": "redis://:pw@{host}:6379/0",
    "minio_endpoint": "http://{host}:9000",
    "frontend_base_url": "https://{host}",
    "cors_origins": "https://{host}",
    "comms_redis_url": "redis://:pw@{host}:6379/0",
    "comms_api_url": "http://{host}:8000",
    "payments_api_url": "http://{host}:8000",
}

_LOOPBACK_HOSTS = [
    "localhost",
    "LOCALHOST",
    "app.localhost",
    "127.0.0.1",
    "127.1.2.3",
    "[::1]",
    "0.0.0.0",
]


@pytest.mark.parametrize("field", list(_URL_SHAPES))
@pytest.mark.parametrize("host", _LOOPBACK_HOSTS)
def test_production_refuses_a_loopback_url(
    monkeypatch: pytest.MonkeyPatch, field: str, host: str,
) -> None:
    """Inside the container a loopback host is the container itself. Every
    URL setting refuses it in every spelling -- this is the form the
    development defaults take (localhost:5173, redis://localhost,
    localhost:9000, the dev DATABASE_URL)."""
    _scrub(monkeypatch)
    message = _refusal(**{
        **_GOOD_OPTIONAL_STACKS,
        field: _URL_SHAPES[field].format(host=host),
    })
    assert _ENV_NAME[field] in message
    assert "loopback" in message


def test_production_refuses_every_development_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The values a development box is filled with are refused when set
    explicitly on any other box -- the same constants serve both
    directions, so the two can never drift apart."""
    _scrub(monkeypatch)
    for field, value in (
        ("database_url", _DEV_DATABASE_URL),
        ("secret_key", _DEV_SECRET_KEY),
        ("minio_endpoint", _DEV_MINIO_ENDPOINT),
        ("minio_access_key", _DEV_MINIO_CREDENTIAL),
        ("minio_secret_key", _DEV_MINIO_CREDENTIAL),
    ):
        assert _ENV_NAME[field] in _refusal(**{field: value})


def test_production_refuses_the_frontend_default_left_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P-116 exactly as observed: FRONTEND_BASE_URL not written, so the
    class default (the vite dev server) reached a password-reset letter."""
    _scrub(monkeypatch)
    values = {"app_env": "production", **_GOOD_REQUIRED, **_NO_OPTIONAL_STACKS}
    del values["frontend_base_url"]
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, **values)
    assert "FRONTEND_BASE_URL" in str(exc.value)


@pytest.mark.parametrize("bad", [
    "http://app.aivis.one",
    "app.aivis.one",
    "https://",
    "https://app.aivis.one/",
    " https://app.aivis.one",
    "https://app.aivis.one ",
])
def test_production_refuses_a_malformed_frontend_base_url(
    monkeypatch: pytest.MonkeyPatch, bad: str,
) -> None:
    """Links are built as <base>/<path>: the base must be an absolute
    https URL with a host, no trailing slash and no surrounding blanks."""
    _scrub(monkeypatch)
    assert "FRONTEND_BASE_URL" in _refusal(frontend_base_url=bad)


@pytest.mark.parametrize("cors, label", [
    ("https://app.aivis.one,", "CORS_ORIGINS entry 2 is empty"),
    (
        "https://app.aivis.one,http://localhost:5173",
        "CORS_ORIGINS entry 2 points at a loopback",
    ),
    ("PLACEHOLDER", "CORS_ORIGINS is a placeholder"),
])
def test_production_judges_every_cors_origin(
    monkeypatch: pytest.MonkeyPatch, cors: str, label: str,
) -> None:
    """Each listed origin is judged like any other URL, and the refusal
    says which entry; the wildcard keeps its own message (covered by
    test_settings_non_development_is_production_grade)."""
    _scrub(monkeypatch)
    assert label in _refusal(cors_origins=cors)


def test_production_names_every_problem_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One refusal names ALL unfit settings, each exactly once, so a single
    start shows the whole list rather than one name per attempt."""
    _scrub(monkeypatch)
    message = _refusal(
        telegram_bot_token="PLACEHOLDER",
        frontend_base_url="http://localhost:5173",
        redis_url="redis://localhost:6379/0",
        secret_key="",
    )
    for name in (
        "TELEGRAM_BOT_TOKEN", "FRONTEND_BASE_URL", "REDIS_URL", "SECRET_KEY",
    ):
        assert message.count(f"{name} ") == 1, name
    for name in ("DATABASE_URL", "MINIO_ENDPOINT", "CORS_ORIGINS"):
        assert f"{name} " not in message, name


def test_development_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """In development nothing new is refused: placeholders, localhost and
    empty values pass, empties get the development fallbacks, and every
    other value comes out exactly as given."""
    _scrub(monkeypatch)
    s = Settings(
        _env_file=None,
        app_env="development",
        cors_origins="*",
        frontend_base_url="http://localhost:5173",
        redis_url="redis://localhost:6379/0",
        telegram_bot_token="PLACEHOLDER",
        comms_api_url="",
        comms_service_token="",
        payments_api_url="",
        payments_service_token="",
        payments_webhook_secret="",
        database_url="",
        secret_key="",
        minio_endpoint="",
        minio_access_key="",
        minio_secret_key="",
    )
    assert s.is_dev is True
    assert s.frontend_base_url == "http://localhost:5173"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.telegram_bot_token == "PLACEHOLDER"
    assert s.database_url == _DEV_DATABASE_URL
    assert s.secret_key == _DEV_SECRET_KEY
    assert s.minio_endpoint == _DEV_MINIO_ENDPOINT
    assert s.minio_access_key == _DEV_MINIO_CREDENTIAL
    assert s.minio_secret_key == _DEV_MINIO_CREDENTIAL
