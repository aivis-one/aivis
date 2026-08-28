# =============================================================================
# AIVIS.ONE Backend -- Password Reset Tests
# =============================================================================
#
# Tests cover:
#   1: Request -> confirm happy path (new password logs in, old one 401s)
#   2: Anti-enumeration -- identical response for a real vs a fake email
#   3: Expired token -> 400 on confirm
#   4: Already-used token -> second confirm -> 400
#   5: Rate limiting on the request endpoint (shared "password_reset:{ip}"
#      key with confirm, see auth/router.py header)
#
# Both endpoints are UNAUTHENTICATED (see auth/service.py's "PASSWORD
# RESET" module note) -- no auth_headers() anywhere in this file.
#
# The request endpoint's fixed response means tests cannot read the
# token off the HTTP response (that is the whole point -- anti-
# enumeration). Instead, `capture_reset_email` monkeypatches
# _send_password_reset_email (the same target the autouse mock_email
# fixture already no-ops) with a fake that records (email, token) into
# a dict the test can read after the request call returns.
#
# Email prefix: "pwreset_" -- unique to this test file.
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.redis import get_redis
from app.modules.auth.service import _PASSWORD_RESET_REDIS_PREFIX
from tests.helpers import auth_headers, login_user, register_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def capture_reset_email(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Capture the (email, token) pair the service would have emailed.

    Overrides the no-op the autouse `mock_email` fixture already
    installed -- monkeypatch.setattr layers fine, whichever call
    happens last (this fixture, applied after autouse fixtures for
    tests that request it) wins for the duration of the test.
    """
    captured: dict = {}

    async def _fake(email: str, token: str) -> None:
        captured["email"] = email
        captured["token"] = token

    monkeypatch.setattr(
        "app.modules.auth.service._send_password_reset_email", _fake
    )
    return captured


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _request_reset(client: AsyncClient, email: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": email},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_happy_path(
    client: AsyncClient, capture_reset_email: dict
) -> None:
    """Request -> confirm with a fresh password -> old password rejected,
    new password logs in, and every prior session is invalidated.
    """
    email = f"pwreset_happy_{uuid.uuid4().hex[:12]}@example.com"
    old_password = "OldPassword123"
    new_password = "NewPassword456"

    data = await register_user(client, email=email, password=old_password)
    old_token = data["session_token"]

    body = await _request_reset(client, email)
    assert body == {
        "message": (
            "If that email is registered, a password reset link has "
            "been sent."
        )
    }
    assert capture_reset_email["email"] == email
    reset_token = capture_reset_email["token"]
    assert len(reset_token) > 20  # secrets.token_urlsafe(32), not a 6-digit code

    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": new_password},
    )
    assert resp.status_code == 204, resp.text

    # Old password no longer authenticates.
    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": old_password},
    )
    assert resp.status_code == 401

    # New password does.
    await login_user(client, email=email, password=new_password)

    # The session that existed BEFORE the reset must not survive it.
    resp = await client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(old_token),
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reset_confirm_invalid_token(client: AsyncClient) -> None:
    """Confirm with a token nobody ever issued -> 400."""
    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "not-a-real-token", "new_password": "WhateverPass1"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Anti-enumeration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_request_same_response_real_vs_fake_email(
    client: AsyncClient, capture_reset_email: dict
) -> None:
    """A real account's email and a never-registered email must produce
    byte-identical status + body -- the entire point of P-anti-enum.

    Also confirms the internal branch actually happened (email fired
    only for the real address) so this test is not accidentally
    passing because NEITHER branch does anything.
    """
    real_email = f"pwreset_real_{uuid.uuid4().hex[:12]}@example.com"
    fake_email = f"pwreset_ghost_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=real_email)

    real_resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": real_email},
    )
    real_captured_email = capture_reset_email.get("email")
    capture_reset_email.clear()

    fake_resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": fake_email},
    )
    fake_captured_email = capture_reset_email.get("email")

    assert real_resp.status_code == fake_resp.status_code == 200
    assert real_resp.json() == fake_resp.json()

    # The internal branch DID differ -- proves the test exercises the
    # real "match found" vs "no match" code paths, not two no-ops.
    assert real_captured_email == real_email
    assert fake_captured_email is None


# ---------------------------------------------------------------------------
# Expired / already-used tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_confirm_expired_token(
    client: AsyncClient, capture_reset_email: dict
) -> None:
    """A token whose Redis key has expired -> 400 on confirm.

    Redis TTL is 30 minutes (_PASSWORD_RESET_TOKEN_TTL_MINUTES) -- far
    too long to actually wait out in a test. Deleting the key directly
    exercises the IDENTICAL code path real expiry hits: confirm_
    password_reset()'s only signal is `redis.getdel(key) is None`,
    which is exactly what a naturally-expired key also returns. This is
    not a weaker test than waiting 30 minutes would be -- it is the
    same assertion reached the fast way.
    """
    email = f"pwreset_expired_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    await _request_reset(client, email)
    token = capture_reset_email["token"]

    redis = get_redis()
    deleted = await redis.delete(f"{_PASSWORD_RESET_REDIS_PREFIX}{token}")
    assert deleted == 1, "the token must have actually been in Redis to delete"

    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "SomeNewPass1"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_confirm_token_is_single_use(
    client: AsyncClient, capture_reset_email: dict
) -> None:
    """A second confirm with the same (already-consumed) token -> 400.

    This is the single-use guarantee point 4 of the task requires:
    GETDEL means the first confirm's read also deletes the key, so a
    replay -- whether an attacker capturing the link in transit or the
    user double-clicking -- cannot succeed twice.
    """
    email = f"pwreset_reuse_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)

    await _request_reset(client, email)
    token = capture_reset_email["token"]

    first = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "FirstNewPass1"},
    )
    assert first.status_code == 204, first.text

    second = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "SecondNewPass1"},
    )
    assert second.status_code == 400


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_request_rate_limit(client: AsyncClient) -> None:
    """More requests than auth_rate_limit_max_requests -> 429.

    Same shared "password_reset:{ip}" key the confirm endpoint also
    hits (see auth/router.py header) -- exercised here via request only,
    mirroring test_auth_telegram.py::test_telegram_rate_limit's shape
    for the equivalent Telegram-side limiter.
    """
    max_requests = settings.auth_rate_limit_max_requests

    for _ in range(max_requests):
        resp = await client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": f"pwreset_rl_{uuid.uuid4().hex[:12]}@example.com"},
        )
        assert resp.status_code == 200

    resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": f"pwreset_rl_{uuid.uuid4().hex[:12]}@example.com"},
    )
    assert resp.status_code == 429
    assert resp.json()["error"] == "rate_limit_exceeded"
    retry_after = resp.headers.get("retry-after")
    assert retry_after is not None, "429 must include a Retry-After header"
    assert int(retry_after) > 0


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_request_invalid_email(client: AsyncClient) -> None:
    """Malformed email in the request body -> 422 (Pydantic, not the
    service -- schema validation happens before anti-enumeration logic
    ever runs, so this is exempt from the "same response" rule).
    """
    resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "not-an-email"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reset_confirm_weak_password(
    client: AsyncClient, capture_reset_email: dict
) -> None:
    """new_password < 8 chars -> 422, mirroring EmailRegisterRequest's
    own min_length=8 (PasswordResetConfirmRequest.new_password reuses
    the exact same constraint, not a duplicated rule)."""
    email = f"pwreset_weak_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=email)
    await _request_reset(client, email)
    token = capture_reset_email["token"]

    resp = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "short"},
    )
    assert resp.status_code == 422
