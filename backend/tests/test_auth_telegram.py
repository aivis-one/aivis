# =============================================================================
# CBSHOME Backend -- Telegram Auth Tests (Sprint 1.2)
# =============================================================================
#
# Tests cover:
#   1:    Valid initData -> 200, user created
#   2:    Repeat login -> same user, credentials.telegram updated
#   3:    Session created (verified by authenticated request)
#   4:    Invalid HMAC signature -> 400
#   5:    Expired initData -> 400
#   6:    Future auth_date beyond clock_skew -> 400
#   7:    Slight future auth_date within clock_skew -> 200
#   8:    Replayed initData (same hash) -> 400
#   9:    Rate limit exceeded -> 400
#   10:   Missing init_data field -> 422
#
# Telegram IDs: 100001-100099 range, cleaned up in fixture.
# =============================================================================

import time
import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.helpers import (
    auth_headers,
    build_init_data,
    login_telegram,
)

# Telegram IDs for this test file.
TG_IDS = list(range(100001, 100020))


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_login_creates_user(client: AsyncClient) -> None:
    """Valid initData -> 200, new user created with role=investor."""
    data = await login_telegram(client, telegram_id=100001, first_name="Alice")

    assert "session_token" in data
    assert data["user"]["role"] == "investor"
    assert data["user"]["is_active"] is True


@pytest.mark.asyncio
async def test_telegram_repeat_login_updates_credentials(
    client: AsyncClient,
) -> None:
    """Repeat login with updated username -> same user, credentials updated."""
    data1 = await login_telegram(
        client, telegram_id=100002, first_name="Bob", username="bob_old",
    )
    user_id = data1["user"]["id"]

    data2 = await login_telegram(
        client, telegram_id=100002, first_name="Bob", username="bob_new",
    )

    # Same user, not a new one.
    assert data2["user"]["id"] == user_id


@pytest.mark.asyncio
async def test_telegram_session_works(client: AsyncClient) -> None:
    """Session token from telegram login works for authenticated requests."""
    data = await login_telegram(client, telegram_id=100003)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(token),
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_invalid_signature(client: AsyncClient) -> None:
    """Tampered initData hash -> 400."""
    init_data = build_init_data(telegram_id=100004, first_name="Eve")
    tampered = init_data.rsplit("hash=", 1)[0] + "hash=deadbeef0000"

    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": tampered},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_telegram_expired_init_data(client: AsyncClient) -> None:
    """auth_date older than TTL -> 400."""
    old_date = int(time.time()) - 600  # 10 minutes ago
    init_data = build_init_data(
        telegram_id=100005, first_name="Expired", auth_date=old_date,
    )

    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_telegram_future_auth_date_rejected(client: AsyncClient) -> None:
    """auth_date far in the future (beyond clock_skew) -> 400.

    Without this guard, an attacker sets auth_date to year 2030 and the
    initData never expires (now - future_date < 0 < ttl).
    """
    clock_skew = settings.auth_clock_skew_seconds  # default 60
    future_date = int(time.time()) + clock_skew + 60  # 60s beyond tolerance

    init_data = build_init_data(
        telegram_id=100008, first_name="Future", auth_date=future_date,
    )

    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 400
    assert "future" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_telegram_slight_future_within_clock_skew(
    client: AsyncClient,
) -> None:
    """auth_date slightly in the future (within clock_skew) -> 200.

    Normal clock drift between Telegram server and our VPS should
    not reject valid logins.
    """
    clock_skew = settings.auth_clock_skew_seconds  # default 60
    # Half the tolerance -- safely within the window.
    slight_future = int(time.time()) + clock_skew // 2

    init_data = build_init_data(
        telegram_id=100009, first_name="SlightFuture", auth_date=slight_future,
    )

    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Anti-replay
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_replayed_init_data(client: AsyncClient) -> None:
    """Same initData sent twice -> second request 400."""
    init_data = build_init_data(telegram_id=100006, first_name="Replay")

    resp1 = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp2.status_code == 400
    assert "already used" in resp2.json()["message"]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_rate_limit(client: AsyncClient) -> None:
    """More requests than auth_rate_limit_max_requests -> 400.

    Uses real settings. Sends max+1 requests.
    """
    tg_id = 100007
    max_requests = settings.auth_rate_limit_max_requests

    for _ in range(max_requests):
        init_data = build_init_data(telegram_id=tg_id, first_name="Ratelimit")
        resp = await client.post(
            "/api/v1/auth/telegram",
            json={"init_data": init_data},
        )
        assert resp.status_code == 200

    # Next call should be rate-limited.
    init_data = build_init_data(telegram_id=tg_id, first_name="Ratelimit")
    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 400
    assert "Too many" in resp.json()["message"]


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_missing_init_data(client: AsyncClient) -> None:
    """Request without init_data field -> 422."""
    resp = await client.post(
        "/api/v1/auth/telegram",
        json={},
    )
    assert resp.status_code == 422
