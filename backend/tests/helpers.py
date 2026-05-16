# =============================================================================
# CBSHOME Backend -- Test Helpers (post iter 2.5 mini-fix #3)
# =============================================================================
#
# This module used to contain ~400 lines of cleanup_test_users and friends
# -- functions whose only job was hand-deleting rows in the right order
# from a shared dev database that tests had polluted. After the conftest
# rewrite moved tests to per-worker ephemeral databases, those cleanups
# are dead code: the whole DB disappears in pytest_unconfigure.
#
# What remains here is the small set of HTTP / auth helpers that test
# bodies actually call. These are honest helpers, not cleanup glue.
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.staff.models import StaffProfile
from app.modules.users.models import (
    KYCStatus,
    OnboardingStep,
    User,
    UserRole,
)


# ---------------------------------------------------------------------------
# Telegram initData fabrication
# ---------------------------------------------------------------------------

# Same dev-only token as tests/test_auth_telegram.py historical default.
# A real token in production is enforced by config validation.
BOT_TOKEN = settings.telegram_bot_token or "TEST"

# Monotonic counter so back-to-back build_init_data() calls do not
# produce duplicate auth_date / hash collisions inside a single test.
_init_data_counter = 0


def build_init_data(
    telegram_id: int,
    first_name: str = "Test",
    last_name: str = "User",
    username: str | None = None,
    language: str = "en",
    auth_date: int | None = None,
) -> str:
    """Forge a Telegram WebApp initData string signed with BOT_TOKEN.

    Mirrors the algorithm the real client uses: build a sorted
    key=value\n list of all fields except `hash`, sign with
    HMAC-SHA256(secret_key, payload), where secret_key =
    HMAC-SHA256("WebAppData", bot_token).
    """
    global _init_data_counter
    _init_data_counter += 1

    auth_date = auth_date or (int(time.time()) - _init_data_counter)
    user_obj = {
        "id": telegram_id,
        "first_name": first_name,
        "last_name": last_name,
        "language_code": language,
    }
    if username is not None:
        user_obj["username"] = username

    # Compact JSON, no spaces -- this is what real Telegram sends.
    import json

    user_json = json.dumps(user_obj, separators=(",", ":"))

    parts = {
        "user": user_json,
        "auth_date": str(auth_date),
        "query_id": f"q{telegram_id}_{_init_data_counter}",
    }

    data_check_string = "\n".join(
        f"{k}={parts[k]}" for k in sorted(parts.keys())
    )

    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    signature = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    from urllib.parse import urlencode

    return urlencode({**parts, "hash": signature})


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------


def auth_headers(token: str) -> dict[str, str]:
    """Build the standard Authorization header used by every test."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Email auth helpers
# ---------------------------------------------------------------------------


async def register_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Password123!",
    referral_code: str | None = None,
) -> dict:
    """POST /api/v1/auth/email/register and assert 201. Returns the
    response body (contains session_token and user details).

    If email is omitted, a UUID-suffixed unique email is generated. This
    is the default path -- tests that need a specific email (e.g. to
    check duplicate-rejection or to re-use the same address across two
    register calls) pass email= explicitly.
    """
    if email is None:
        email = f"test_{uuid.uuid4().hex[:12]}@example.com"
    payload: dict[str, str] = {"email": email, "password": password}
    if referral_code:
        payload["referral_code"] = referral_code

    resp = await client.post("/api/v1/auth/email/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Echo the email back into the response so callers that did not
    # pre-generate it can still find out what was used.
    body.setdefault("email", email)
    return body


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = "Password123!",
) -> dict:
    """POST /api/v1/auth/email/login and assert 200."""
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Telegram auth helpers
# ---------------------------------------------------------------------------


async def login_telegram(
    client: AsyncClient,
    *,
    telegram_id: int,
    first_name: str = "Test",
    last_name: str = "User",
    username: str | None = None,
    language: str = "en",
    referral_code: str | None = None,
) -> dict:
    """POST /api/v1/auth/telegram/login with forged initData. Asserts
    2xx and returns the response body.
    """
    init_data = build_init_data(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        language=language,
    )
    payload: dict[str, str] = {"init_data": init_data}
    if referral_code:
        payload["referral_code"] = referral_code

    resp = await client.post("/api/v1/auth/telegram/login", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Staff / admin factory helpers
# ---------------------------------------------------------------------------


async def create_staff_user(
    client: AsyncClient,
    session: AsyncSession,
    *,
    email: str | None = None,
    password: str = "Password123!",
) -> tuple[User, str]:
    """Register a regular user, then promote to staff by inserting a
    StaffProfile with no special permissions. Returns (User, token).

    If email is omitted, a UUID-suffixed unique email is generated.
    """
    if email is None:
        email = f"staff_{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    result = await session.execute(
        select(User).where(
            User.credentials["email"]["email"].as_string() == email
        )
    )
    user = result.scalar_one()
    user.role = UserRole.STAFF
    user.onboarding_step = OnboardingStep.COMPLETED
    user.kyc_status = KYCStatus.APPROVED

    profile = StaffProfile(
        id=uuid.uuid4(),
        user_id=user.id,
        # Defaults are all False; specific tests bump them up.
    )
    session.add(profile)
    await session.commit()
    return user, token


async def create_admin_user(
    client: AsyncClient,
    session: AsyncSession,
    *,
    email: str | None = None,
    password: str = "Password123!",
) -> tuple[User, str]:
    """Like create_staff_user, but flips every StaffProfile permission
    to True so the resulting account is a full admin.

    If email is omitted, a UUID-suffixed unique email is generated.
    """
    if email is None:
        email = f"admin_{uuid.uuid4().hex[:12]}@example.com"
    user, token = await create_staff_user(
        client, session, email=email, password=password
    )

    result = await session.execute(
        select(StaffProfile).where(StaffProfile.user_id == user.id)
    )
    profile = result.scalar_one()

    # Flip every Boolean column on the profile (defensive against future
    # permission additions; tests that opt into admin really want them all).
    for col in profile.__table__.columns:
        if col.type.python_type is bool:
            setattr(profile, col.name, True)

    await session.commit()
    await session.refresh(profile)
    return user, token
