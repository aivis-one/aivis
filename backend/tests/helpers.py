# =============================================================================
# CBSHOME Backend -- Shared Test Helpers
# =============================================================================
#
# Utility functions used across multiple test files.
# Not a conftest (no fixtures) -- just plain functions.
#
# EMAIL AUTH:
#   register_user() and login_user() call the email auth endpoints.
#
# TELEGRAM AUTH (Sprint 1.2):
#   build_init_data() creates a valid signed Telegram initData string.
#   BOT_TOKEN is read from settings to match the runtime token (may differ
#   between dev and VPS -- .env sets the real token on prod).
#   _init_data_counter ensures unique query_id on every call to avoid
#   anti-replay rejection when multiple calls happen in the same second.
# =============================================================================

import hashlib
import hmac
import itertools
import json
import time
from urllib.parse import urlencode

from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLog
from app.core.config import settings
from app.modules.users.models import User

# Read from settings -- must match the token used by the router
# for HMAC validation. On VPS this is the real bot token from .env.
BOT_TOKEN = settings.telegram_bot_token

# Module-level counter: unique query_id per build_init_data() call.
_init_data_counter = itertools.count(1)


def auth_headers(token: str) -> dict[str, str]:
    """Build Authorization header dict for test requests."""
    return {"Authorization": f"Bearer {token}"}


def build_init_data(
    user_data: dict,
    bot_token: str = BOT_TOKEN,
    auth_date: int | None = None,
) -> str:
    """Build a valid Telegram initData query string with correct HMAC.

    Includes a unique query_id on every call (via _init_data_counter) so
    that multiple calls for the same telegram_id within the same second
    produce different hashes and don't trigger anti-replay protection.
    """
    if auth_date is None:
        auth_date = int(time.time())

    query_id = str(next(_init_data_counter))

    params = {
        "user": json.dumps(user_data, separators=(",", ":")),
        "auth_date": str(auth_date),
        "query_id": query_id,
    }

    # Build data-check-string: sorted key=value pairs joined by \n.
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )

    # Compute HMAC-SHA256.
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256,
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256,
    ).hexdigest()

    params["hash"] = computed_hash
    return urlencode(params)


async def register_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpass123",
) -> dict:
    """Register a user via POST /api/v1/auth/email/register.

    Returns the parsed AuthResponse dict.
    Raises AssertionError if status != 201.
    """
    resp = await client.post(
        "/api/v1/auth/email/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201, f"Register failed: {resp.status_code} {resp.text}"
    return resp.json()


async def login_user(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "testpass123",
) -> dict:
    """Login a user via POST /api/v1/auth/email/login.

    Returns the parsed AuthResponse dict.
    Raises AssertionError if status != 200.
    """
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()


async def login_telegram(
    client: AsyncClient,
    telegram_id: int,
    first_name: str = "Test",
    username: str | None = None,
) -> dict:
    """Login via POST /api/v1/auth/telegram.

    Returns the parsed AuthResponse dict.
    Raises AssertionError if status != 200.
    """
    user_data = {"id": telegram_id, "first_name": first_name}
    if username:
        user_data["username"] = username

    init_data = build_init_data(user_data)
    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 200, f"Telegram login failed: {resp.status_code} {resp.text}"
    return resp.json()


async def cleanup_test_users(
    session: AsyncSession,
    email_prefix: str,
) -> None:
    """Delete test users whose email starts with the given prefix.

    Also cleans up related audit_log entries (actor_id or target_id).
    Uses ORM delete (no raw SQL).
    """
    stmt = select(User.id).where(
        User.credentials["email"]["email"].as_string().startswith(email_prefix)
    )
    result = await session.execute(stmt)
    user_ids = [row[0] for row in result.all()]

    if not user_ids:
        return

    await session.execute(
        delete(AuditLog).where(
            AuditLog.actor_id.in_(user_ids) | AuditLog.target_id.in_(user_ids)
        )
    )

    await session.execute(
        delete(User).where(User.id.in_(user_ids))
    )

    await session.commit()


async def cleanup_telegram_test_users(
    session: AsyncSession,
    telegram_ids: list[int],
) -> None:
    """Delete test users by telegram_id in credentials JSONB.

    Also cleans up related audit_log entries.
    """
    if not telegram_ids:
        return

    user_ids = []
    for tg_id in telegram_ids:
        stmt = select(User.id).where(
            User.credentials["telegram"]["id"].as_integer() == tg_id
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            user_ids.append(row)

    if not user_ids:
        return

    await session.execute(
        delete(AuditLog).where(
            AuditLog.actor_id.in_(user_ids) | AuditLog.target_id.in_(user_ids)
        )
    )

    await session.execute(
        delete(User).where(User.id.in_(user_ids))
    )

    await session.commit()
