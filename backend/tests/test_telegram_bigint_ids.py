# =============================================================================
# CBSHOME Backend -- Telegram BIGINT id Regression Tests (Task 1 drive-by)
# =============================================================================
#
# Regression guard for the int32 lookup bug found during Task 1:
# upsert_telegram_user looked users up via as_integer() -- CAST(... AS
# INTEGER) -- so any real-world Telegram id above 2_147_483_647 blew up
# at the asyncpg int4 bind and the login returned 500. The functional
# index ix_users_telegram_id (migration 0002) was bigint all along; the
# fix casts the lookup to BIGINT.
#
# These tests pin the fix with ids that are guaranteed > int32 max.
# Candidate for merging into tests/test_auth_telegram.py later.
# =============================================================================

from __future__ import annotations

import secrets

from httpx import AsyncClient

from tests.helpers import login_telegram

_INT32_MAX = 2_147_483_647


def _big_telegram_id() -> int:
    """Random id strictly above int32 max (matches modern Telegram ids)."""
    return _INT32_MAX + 1 + secrets.randbelow(5_000_000_000)


async def test_telegram_login_with_id_above_int32(
    client: AsyncClient,
) -> None:
    """First login with a >int32 telegram id -> user created, no 500."""
    data = await login_telegram(client, telegram_id=_big_telegram_id())

    assert "session_token" in data
    assert data["user"]["role"] == "investor"


async def test_telegram_repeat_login_with_id_above_int32(
    client: AsyncClient,
) -> None:
    """Repeat login with the same >int32 id -> SAME user found via the
    BIGINT lookup (the lookup path, not just the insert, must survive).
    """
    tg_id = _big_telegram_id()

    first = await login_telegram(client, telegram_id=tg_id)
    second = await login_telegram(client, telegram_id=tg_id)

    assert second["user"]["id"] == first["user"]["id"]
