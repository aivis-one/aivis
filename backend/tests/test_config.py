# =============================================================================
# CBSHOME Backend -- Config Tests (R51)
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
#
# These construct Settings directly with _env_file=None and a scrubbed
# APP_ENV so the container's real environment never leaks in.
# =============================================================================

import pytest
from pydantic import ValidationError

from app.core.config import Settings


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

    # A typo'd / staging value is production-grade: the very first
    # production requirement (CORS) fires.
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, app_env="staging")
    assert "CORS_ORIGINS" in str(exc.value)
