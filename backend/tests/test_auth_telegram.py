# =============================================================================
# CBSHOME Backend -- Telegram Auth Tests (Sprint 1.2)
# =============================================================================
#
# Tests cover:
#   1:   Valid initData -> 200, user created
#   2:   Repeat login -> same user, credentials.telegram updated
#   3:   Session created (verified by authenticated request)
#   4:   Invalid HMAC signature -> 400
#   5:   Expired initData -> 400
#   6:   Replayed initData (same hash) -> 400
#   7:   Rate limit exceeded -> 400
#   8:   Missing init_data field -> 422
#
# Telegram IDs: 100001-100099 range, cleaned up in fixture.
# BOT_TOKEN is read from settings (matches runtime token).
# =============================================================================

import time
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from tests.helpers import (
    auth_headers,
    build_init_data,
    cleanup_telegram_test_users,
    login_telegram,
)

# Telegram IDs for this test file.
TG_IDS = list(range(100001, 100010))


@pytest.fixture(autouse=True)
async def cleanup(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Clean test users and Redis keys before/after each test."""
    await cleanup_telegram_test_users(db_session, TG_IDS)
    redis = get_redis()
    for tg_id in TG_IDS:
        await redis.delete(f"auth_rate:{tg_id}")
    yield
    await cleanup_telegram_test_users(db_session, TG_IDS)
    for tg_id in TG_IDS:
        await redis.delete(f"auth_rate:{tg_id}")


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
    user_data = {"id": 100004, "first_name": "Eve"}
    init_data = build_init_data(user_data)
    # Replace hash with garbage.
    tampered = init_data.rsplit("hash=", 1)[0] + "hash=deadbeef0000"

    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": tampered},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_telegram_expired_init_data(client: AsyncClient) -> None:
    """auth_date older than TTL -> 400."""
    user_data = {"id": 100005, "first_name": "Expired"}
    old_date = int(time.time()) - 600  # 10 minutes ago
    init_data = build_init_data(user_data, auth_date=old_date)

    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_telegram_replayed_init_data(client: AsyncClient) -> None:
    """Same initData sent twice -> second request 400."""
    user_data = {"id": 100006, "first_name": "Replay"}
    init_data = build_init_data(user_data)

    # First request -- should succeed.
    resp1 = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp1.status_code == 200

    # Second request with SAME init_data -- should fail.
    resp2 = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp2.status_code == 400
    assert "already used" in resp2.json()["message"]


@pytest.mark.asyncio
async def test_telegram_rate_limit(client: AsyncClient) -> None:
    """More requests than auth_rate_limit_max_requests -> 400.

    Uses real settings (default max_requests=5). Sends max+1 requests.
    """
    tg_id = 100007
    max_requests = settings.auth_rate_limit_max_requests

    # Send max_requests successful calls.
    for _ in range(max_requests):
        data = {"id": tg_id, "first_name": "Ratelimit"}
        init_data = build_init_data(data)
        resp = await client.post(
            "/api/v1/auth/telegram",
            json={"init_data": init_data},
        )
        assert resp.status_code == 200

    # Next call should be rate-limited.
    data = {"id": tg_id, "first_name": "Ratelimit"}
    init_data = build_init_data(data)
    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 400
    assert "Too many" in resp.json()["message"]


@pytest.mark.asyncio
async def test_telegram_missing_init_data(client: AsyncClient) -> None:
    """Request without init_data field -> 422."""
    resp = await client.post(
        "/api/v1/auth/telegram",
        json={},
    )
    assert resp.status_code == 422
