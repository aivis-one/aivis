# =============================================================================
# AIVIS.ONE Backend -- Email Change Tests (TASK-38)
# =============================================================================
#
# Tests cover:
#   1: Happy path -- request -> confirm swaps the login email; old email
#      no longer logs in, new email does
#   2: Wrong current password on request -> 403 incorrect_password,
#      no pending change is created
#   3: New email identical to the current one -> 400
#   4: New email already registered to ANOTHER account -> 409
#   5: Resend regenerates the code -- the OLD code stops working, the
#      NEW one confirms
#   6: Confirm with no pending change -> 400
#   7: Confirm with an expired code -> 400
#   8: Confirm attempts cap -> 400 after 5 wrong codes
#   9: Rate limit on the request endpoint (email_change_request:{user.id})
#  10: Malformed new_email -> 422
#  11: Confirm success kills EVERY session (including a second, separate
#      one for the same user) and schedules a notice to the OLD address
#      (Navigator-30's TASK-38 review -- both were missing originally)
#
# Email prefix: "echange_" -- unique to this test file.
#
# mock_email (conftest.py, autouse) already no-ops
# _send_email_change_verification_email; tests that need the actual
# code monkeypatch it again with a capturing fake, same layering
# pattern as test_auth_password_reset.py's capture_reset_email.
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.users.models import User
from tests.helpers import auth_headers, login_user, register_user

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def capture_change_email(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Capture the (email, code) pair the service would have emailed.

    Overrides the no-op the autouse `mock_email` fixture installed for
    `app.modules.users.service._send_email_change_verification_email`.
    """
    captured: dict = {}

    async def _fake(email: str, code: str) -> None:
        captured["email"] = email
        captured["code"] = code

    monkeypatch.setattr(
        "app.modules.users.service._send_email_change_verification_email",
        _fake,
    )
    return captured


async def _request_change(
    client: AsyncClient,
    token: str,
    *,
    current_password: str = "Password123!",
    new_email: str | None = None,
) -> dict:
    if new_email is None:
        new_email = f"echange_new_{uuid.uuid4().hex[:12]}@example.com"
    resp = await client.post(
        "/api/v1/users/me/email-change",
        json={"current_password": current_password, "new_email": new_email},
        headers=auth_headers(token),
    )
    assert resp.status_code == 204, resp.text
    return {"new_email": new_email}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_happy_path(
    client: AsyncClient, capture_change_email: dict
) -> None:
    """Request -> confirm with the emailed code -> login moves to the
    new address, the old one is rejected.
    """
    old_email = f"echange_old_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=old_email, password=password)
    token = data["session_token"]

    new_email = f"echange_new_{uuid.uuid4().hex[:12]}@example.com"
    await _request_change(
        client, token, current_password=password, new_email=new_email
    )
    assert capture_change_email["email"] == new_email
    code = capture_change_email["code"]
    assert len(code) == 6 and code.isdigit()

    resp = await client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"code": code},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == new_email

    # Old email no longer authenticates.
    old_login = await client.post(
        "/api/v1/auth/email/login",
        json={"email": old_email, "password": password},
    )
    assert old_login.status_code == 401

    # New email does, same password.
    await login_user(client, email=new_email, password=password)


# ---------------------------------------------------------------------------
# Re-authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_wrong_current_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Wrong current_password on request -> 403 incorrect_password, and
    no pending change is written (credentials.email_change stays absent).
    """
    email = f"echange_wrongpw_{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email=email)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/email-change",
        json={
            "current_password": "definitely-not-it",
            "new_email": f"echange_target_{uuid.uuid4().hex[:12]}@example.com",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "incorrect_password"

    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    assert user.credentials.get("email_change") is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_same_as_current(client: AsyncClient) -> None:
    """new_email == current login email -> 400."""
    email = f"echange_same_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/email-change",
        json={"current_password": password, "new_email": email},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_email_change_target_already_registered(client: AsyncClient) -> None:
    """new_email already belongs to ANOTHER account -> 409."""
    other_email = f"echange_taken_{uuid.uuid4().hex[:12]}@example.com"
    await register_user(client, email=other_email)

    email = f"echange_requester_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/email-change",
        json={"current_password": password, "new_email": other_email},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_email_change_invalid_new_email(client: AsyncClient) -> None:
    """Malformed new_email -> 422 (Pydantic EmailStr)."""
    email = f"echange_badfmt_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/email-change",
        json={"current_password": password, "new_email": "not-an-email"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Resend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_resend_invalidates_old_code(
    client: AsyncClient, capture_change_email: dict
) -> None:
    """Resend regenerates the code -- the OLD one no longer confirms,
    the NEW one does.
    """
    email = f"echange_resend_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    result = await _request_change(client, token, current_password=password)
    old_code = capture_change_email["code"]
    capture_change_email.clear()

    resend_resp = await client.post(
        "/api/v1/users/me/email-change/resend",
        json={},
        headers=auth_headers(token),
    )
    assert resend_resp.status_code == 204, resend_resp.text
    new_code = capture_change_email["code"]
    assert capture_change_email["email"] == result["new_email"]

    # Old code: rejected (also burns one of the 5 attempts, but that's
    # fine -- the new code below is a fresh, still-unused attempt).
    stale = await client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"code": old_code},
        headers=auth_headers(token),
    )
    assert stale.status_code == 400

    # New code: confirms.
    fresh = await client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"code": new_code},
        headers=auth_headers(token),
    )
    assert fresh.status_code == 200, fresh.text


@pytest.mark.asyncio
async def test_email_change_resend_without_pending_change(client: AsyncClient) -> None:
    """Resend with no pending change on the account -> 400."""
    data = await register_user(client)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/email-change/resend",
        json={},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Confirm -- failure modes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_confirm_without_pending_change(client: AsyncClient) -> None:
    """Confirm with no pending change on the account -> 400."""
    data = await register_user(client)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"code": "123456"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_email_change_confirm_expired_code(
    client: AsyncClient, db_session: AsyncSession, capture_change_email: dict
) -> None:
    """A code whose expires_at has already passed -> 400 on confirm.

    Same technique as test_auth_password_reset.py's expired-token test:
    write an already-past expires_at directly rather than sleeping out
    the real 10-minute TTL -- confirm_email_change()'s only signal is
    `datetime.now(UTC) > expires_at`, which this reaches identically.
    """
    from datetime import UTC, datetime, timedelta

    email = f"echange_expired_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    await _request_change(client, token, current_password=password)

    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    creds = dict(user.credentials)
    email_change = dict(creds["email_change"])
    email_change["expires_at"] = (
        datetime.now(UTC) - timedelta(minutes=1)
    ).isoformat()
    creds["email_change"] = email_change
    user.set_jsonb("credentials", creds)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"code": capture_change_email["code"]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_email_change_confirm_attempts_cap(
    client: AsyncClient, capture_change_email: dict
) -> None:
    """5 wrong codes exhaust the attempts cap -> the 6th (even if right) 400s."""
    email = f"echange_attempts_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    await _request_change(client, token, current_password=password)
    real_code = capture_change_email["code"]

    for _ in range(5):
        resp = await client.post(
            "/api/v1/users/me/email-change/confirm",
            json={"code": "000000" if real_code != "000000" else "111111"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 400

    # Attempts exhausted -- even the REAL code now 400s.
    resp = await client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"code": real_code},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_request_rate_limit(client: AsyncClient) -> None:
    """More requests than auth_rate_limit_max_requests -> 429.

    Keyed per-user (email_change_request:{user.id}), not shared with
    any other test -- each test registers its own fresh user, so no
    conftest cleanup is needed (mirrors why email_verify_resend's
    rate-limit key is never cleared in conftest.py either).
    """
    max_requests = settings.auth_rate_limit_max_requests
    email = f"echange_rl_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    for _ in range(max_requests):
        resp = await client.post(
            "/api/v1/users/me/email-change",
            json={
                "current_password": password,
                "new_email": f"echange_rl_target_{uuid.uuid4().hex[:12]}@example.com",
            },
            headers=auth_headers(token),
        )
        assert resp.status_code == 204, resp.text

    resp = await client.post(
        "/api/v1/users/me/email-change",
        json={
            "current_password": password,
            "new_email": f"echange_rl_target_{uuid.uuid4().hex[:12]}@example.com",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Session invalidation + old-address notice (Navigator-30's TASK-38 review)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_change_confirm_kills_every_session_and_notifies_old_address(
    client: AsyncClient, capture_change_email: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful confirm must (a) kill EVERY session for this user --
    including one that never touched the email-change flow at all, not
    just the requesting token -- and (b) schedule a notice to the OLD
    address. Neither happened in the original TASK-38 delivery;
    Navigator-30's review caught both as a silent-takeover gap (a
    stolen session + the current password could move the account onto
    an attacker email with every other session, including the real
    owner's, left alive and nobody told).
    """
    old_email = f"echange_kill_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=old_email, password=password)
    token_a = data["session_token"]

    # A SECOND, independent session for the same user -- e.g. another
    # device -- that never makes an email-change request itself.
    login_b = await login_user(client, email=old_email, password=password)
    token_b = login_b["session_token"]

    captured_notice: dict = {}

    async def _fake_notice(old: str, new: str) -> None:
        captured_notice["old_email"] = old
        captured_notice["new_email"] = new

    monkeypatch.setattr(
        "app.modules.users.service._send_email_changed_notice", _fake_notice
    )

    new_email = f"echange_kill_new_{uuid.uuid4().hex[:12]}@example.com"
    await _request_change(
        client, token_a, current_password=password, new_email=new_email
    )
    code = capture_change_email["code"]

    resp = await client.post(
        "/api/v1/users/me/email-change/confirm",
        json={"code": code},
        headers=auth_headers(token_a),
    )
    assert resp.status_code == 200, resp.text

    # (a) Both sessions are dead -- the requesting one AND the unrelated one.
    me_a = await client.get("/api/v1/users/me", headers=auth_headers(token_a))
    assert me_a.status_code == 401
    me_b = await client.get("/api/v1/users/me", headers=auth_headers(token_b))
    assert me_b.status_code == 401

    # (b) The OLD address was notified, with the right pair of addresses.
    assert captured_notice["old_email"] == old_email
    assert captured_notice["new_email"] == new_email
