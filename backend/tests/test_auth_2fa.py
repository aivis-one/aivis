# =============================================================================
# AIVIS.ONE Backend -- Two-Factor Authentication (TOTP) Tests (TASK-38)
# =============================================================================
#
# Tests cover:
#   1-2:  Setup generates a real pending secret + provisioning_uri
#   3:    Setup requires the current password
#   4-5:  Confirm with a correct live code enables 2FA and issues
#         backup codes (shown once)
#   6:    Confirm with a WRONG code fails and enables nothing
#   7:    Confirm with no prior setup fails
#   8:    Login on a 2FA-enabled account returns the pending-MFA shape,
#         not a real session
#   9:    login-verify with the right code completes login, returns a
#         real usable session_token
#   10:   login-verify with a wrong code fails and does not leak a
#         session -- AND consumes the pending token (single-use even on
#         failure, see auth/service.py's module note)
#   11:   login-verify with an unknown/expired token fails
#   12:   A backup code works exactly once (second use of the same code
#         fails) -- via login-verify
#   13:   Disable requires the current password
#   14:   Disable requires a valid code (TOTP or backup)
#   15:   Disable with password + valid code actually clears 2FA (login
#         goes back to issuing a real session directly)
#   16:   Trust-model: login-verify is rate-limited (tighter than the
#         shared auth default)
#   17:   Telegram login also honours 2FA on an account that has it
#         enabled (no bypass via the Telegram identity path)
#
# Email prefix: "s38_2fa_" -- unique to this test file.
# =============================================================================

import uuid

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from tests.helpers import auth_headers, build_init_data, register_user


async def _register_and_setup_pending(
    client: AsyncClient, *, password: str = "Password123!"
) -> tuple[str, str, str]:
    """Register a fresh user, POST /2fa/setup, return (token, email, secret)."""
    email = f"s38_2fa_{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"current_password": password},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    secret = resp.json()["secret"]
    return token, email, secret


async def _enable_2fa(
    client: AsyncClient, *, password: str = "Password123!"
) -> tuple[str, str, str, list[str]]:
    """Register + setup + confirm. Returns (token, email, secret, backup_codes)."""
    token, email, secret = await _register_and_setup_pending(client, password=password)

    code = pyotp.TOTP(secret).now()
    resp = await client.post(
        "/api/v1/auth/2fa/confirm",
        json={"code": code},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    backup_codes = resp.json()["backup_codes"]
    return token, email, secret, backup_codes


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_generates_pending_secret_and_uri(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /2fa/setup -> a real base32 secret + a matching provisioning_uri,
    stored PENDING (not yet enabled) in credentials.totp_pending.
    """
    email = f"s38_2fa_{uuid.uuid4().hex[:12]}@example.com"
    password = "Password123!"
    data = await register_user(client, email=email, password=password)
    token = data["session_token"]
    user_id = data["user"]["id"]

    resp = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"current_password": password},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    secret = body["secret"]
    assert len(secret) >= 16
    assert body["provisioning_uri"].startswith("otpauth://totp/")
    assert "AIVIS.ONE" in body["provisioning_uri"]

    # pyotp accepts it -- a real, usable base32 secret, not a placeholder.
    assert pyotp.TOTP(secret).now().isdigit()

    user = (
        await db_session.execute(select(User).where(User.id == uuid.UUID(user_id)))
    ).scalar_one()
    totp_pending = (user.credentials or {}).get("totp_pending") or {}
    assert totp_pending.get("secret_encrypted")
    # Not the raw secret -- it must be encrypted at rest.
    assert totp_pending["secret_encrypted"] != secret
    # Not yet enabled.
    assert not ((user.credentials or {}).get("totp") or {}).get("enabled")


@pytest.mark.asyncio
async def test_setup_requires_correct_current_password(client: AsyncClient) -> None:
    """POST /2fa/setup with the wrong password -> 403, nothing stored."""
    email = f"s38_2fa_{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email=email, password="Password123!")
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"current_password": "totally-wrong"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "incorrect_password"


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_with_correct_code_enables_2fa(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /2fa/confirm with a real, live TOTP code -> 2FA switches on,
    backup codes are issued, and login now requires the second factor.
    """
    _token, email, _secret, backup_codes = await _enable_2fa(client)

    assert len(backup_codes) == 10
    assert len(set(backup_codes)) == 10  # all distinct

    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    totp = (user.credentials or {}).get("totp") or {}
    assert totp.get("enabled") is True
    assert totp.get("enabled_at")
    assert totp.get("secret_encrypted")
    assert len(totp.get("backup_codes") or []) == 10
    # Every backup code hash is unused so far.
    assert all(c["used_at"] is None for c in totp["backup_codes"])
    # Pending slot cleared.
    assert not (user.credentials or {}).get("totp_pending")


@pytest.mark.asyncio
async def test_confirm_with_wrong_code_fails_and_enables_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /2fa/confirm with a wrong code -> 400, 2FA stays off, the
    pending secret is left intact for a retry.
    """
    token, email, _secret = await _register_and_setup_pending(client)

    resp = await client.post(
        "/api/v1/auth/2fa/confirm",
        json={"code": "000000"},
        headers=auth_headers(token),
    )
    # An astronomically unlikely collision with the real code aside,
    # this must fail.
    assert resp.status_code == 400

    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    assert not ((user.credentials or {}).get("totp") or {}).get("enabled")
    # Pending secret survives a wrong guess -- the user can just retry.
    assert (user.credentials or {}).get("totp_pending")


@pytest.mark.asyncio
async def test_confirm_without_prior_setup_fails(client: AsyncClient) -> None:
    """POST /2fa/confirm with no pending setup -> 400."""
    data = await register_user(client)
    token = data["session_token"]

    resp = await client.post(
        "/api/v1/auth/2fa/confirm",
        json={"code": "123456"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Login gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_on_2fa_account_returns_pending_mfa_shape(
    client: AsyncClient,
) -> None:
    """POST /email/login on a 2FA-enabled account -> mfa_required=True,
    an mfa_token, and NO session (user/session_token both null).
    """
    password = "Password123!"
    _token, email, _secret, _codes = await _enable_2fa(client, password=password)

    resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mfa_required"] is True
    assert body["mfa_token"]
    assert body["user"] is None
    assert body["session_token"] is None

    # And the mfa_token is USABLE, not a decoy -- confirmed by the
    # actual login-verify tests below reusing this exact call shape.


@pytest.mark.asyncio
async def test_login_verify_correct_code_completes_login(client: AsyncClient) -> None:
    """POST /2fa/login-verify with the right live code -> a real,
    working session_token (creates a session, same as a normal login).
    """
    password = "Password123!"
    _token, email, secret, _codes = await _enable_2fa(client, password=password)

    login_resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    mfa_token = login_resp.json()["mfa_token"]

    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": mfa_token, "code": code},
    )
    assert verify_resp.status_code == 200, verify_resp.text
    body = verify_resp.json()
    assert body["session_token"]
    assert body["user"]["role"] == "investor"

    # The returned session_token is a REAL, usable session.
    me_resp = await client.get(
        "/api/v1/users/me", headers=auth_headers(body["session_token"])
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email


@pytest.mark.asyncio
async def test_login_verify_wrong_code_fails_no_session_leaked(
    client: AsyncClient,
) -> None:
    """POST /2fa/login-verify with a wrong code -> 400, no session
    created, and the pending token is consumed (a retry with the SAME
    token -- even the right code this time -- also fails).
    """
    password = "Password123!"
    _token, email, secret, _codes = await _enable_2fa(client, password=password)

    login_resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    mfa_token = login_resp.json()["mfa_token"]

    wrong_resp = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": mfa_token, "code": "000000"},
    )
    assert wrong_resp.status_code == 400
    assert "session_token" not in wrong_resp.text

    # The token is now dead -- retrying with the CORRECT code fails too,
    # proving this isn't merely "that one guess was wrong" but "this
    # token no longer exists at all" (see auth/service.py's module note
    # on why the token is consumed on every outcome, not just success).
    real_code = pyotp.TOTP(secret).now()
    retry_resp = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": mfa_token, "code": real_code},
    )
    assert retry_resp.status_code == 400


@pytest.mark.asyncio
async def test_login_verify_unknown_token_fails(client: AsyncClient) -> None:
    """POST /2fa/login-verify with a token that was never issued -> 400."""
    resp = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": "not-a-real-token", "code": "123456"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_backup_code_works_exactly_once(client: AsyncClient) -> None:
    """A backup code completes login-verify once; a second attempt with
    the SAME code (against a fresh mfa_token) fails.
    """
    password = "Password123!"
    _token, email, _secret, backup_codes = await _enable_2fa(client, password=password)
    backup_code = backup_codes[0]

    # First use -- succeeds.
    login_resp1 = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    mfa_token1 = login_resp1.json()["mfa_token"]
    verify_resp1 = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": mfa_token1, "code": backup_code},
    )
    assert verify_resp1.status_code == 200, verify_resp1.text
    assert verify_resp1.json()["session_token"]

    # Second use of the SAME backup code, against a FRESH mfa_token
    # (proving the code itself is spent, not just the earlier token).
    login_resp2 = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    mfa_token2 = login_resp2.json()["mfa_token"]
    verify_resp2 = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": mfa_token2, "code": backup_code},
    )
    assert verify_resp2.status_code == 400


# ---------------------------------------------------------------------------
# Disable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disable_requires_correct_password(client: AsyncClient) -> None:
    """POST /2fa/disable with the wrong password -> 403, 2FA stays on."""
    password = "Password123!"
    token, _email, secret, _codes = await _enable_2fa(client, password=password)
    code = pyotp.TOTP(secret).now()

    resp = await client.post(
        "/api/v1/auth/2fa/disable",
        json={"current_password": "totally-wrong", "code": code},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "incorrect_password"


@pytest.mark.asyncio
async def test_disable_requires_valid_code(client: AsyncClient) -> None:
    """POST /2fa/disable with the right password but a WRONG code -> 400,
    2FA stays on (password alone is not enough).
    """
    password = "Password123!"
    token, email, _secret, _codes = await _enable_2fa(client, password=password)

    resp = await client.post(
        "/api/v1/auth/2fa/disable",
        json={"current_password": password, "code": "000000"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 400

    # Login still requires 2FA -- disable did NOT go through.
    login_resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert login_resp.json()["mfa_required"] is True


@pytest.mark.asyncio
async def test_disable_with_password_and_code_clears_2fa(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /2fa/disable with BOTH factors -> 204, credentials.totp
    cleared, and a subsequent login issues a real session directly
    (no more mfa_required gate).
    """
    password = "Password123!"
    token, email, secret, _codes = await _enable_2fa(client, password=password)
    code = pyotp.TOTP(secret).now()

    resp = await client.post(
        "/api/v1/auth/2fa/disable",
        json={"current_password": password, "code": code},
        headers=auth_headers(token),
    )
    assert resp.status_code == 204

    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    assert not (user.credentials or {}).get("totp")

    # Login goes straight back to a real session.
    login_resp = await client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["mfa_required"] is False
    assert body["session_token"]


@pytest.mark.asyncio
async def test_disable_backup_code_also_accepted(client: AsyncClient) -> None:
    """POST /2fa/disable accepts an unused backup code in place of a
    live TOTP code -- 'a live code OR an unused backup code' per the
    endpoint's contract.
    """
    password = "Password123!"
    token, _email, _secret, backup_codes = await _enable_2fa(client, password=password)

    resp = await client.post(
        "/api/v1/auth/2fa/disable",
        json={"current_password": password, "code": backup_codes[0]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Rate limiting (trust model)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_verify_is_rate_limited(client: AsyncClient) -> None:
    """POST /2fa/login-verify enforces a tighter-than-default IP rate
    limit (5 per 300s, see auth/router.py's auth_2fa_login_verify
    docstring) -- the 6th call within the window gets 429 regardless of
    whether the mfa_token it carries is real.

    Each call below uses a freshly-fabricated (nonexistent) token,
    which the endpoint answers with 400 -- so this test is purely about
    the RATE LIMIT firing before/alongside those 400s, not about a real
    2FA flow. Six is one more than the cap; the sixth response is 429.
    """
    for _ in range(5):
        resp = await client.post(
            "/api/v1/auth/2fa/login-verify",
            json={"mfa_token": f"nope-{uuid.uuid4().hex}", "code": "123456"},
        )
        assert resp.status_code == 400

    limited_resp = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": f"nope-{uuid.uuid4().hex}", "code": "123456"},
    )
    assert limited_resp.status_code == 429


# ---------------------------------------------------------------------------
# Telegram -- no bypass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_login_also_honours_2fa(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A Telegram-linked account with 2FA enabled (via the email/password
    path) must ALSO be gated on POST /auth/telegram -- see the router
    module header's "TELEGRAM ALSO HONOURS 2FA" note. Without this gate,
    anyone who could authenticate as the linked Telegram identity would
    walk straight past a 2FA control the account owner turned on.
    """
    password = "Password123!"
    _token, email, _secret, _codes = await _enable_2fa(client, password=password)

    # Link this account to a Telegram identity directly via the DB --
    # there is no self-service "link Telegram to my existing account"
    # endpoint in this codebase; upsert_telegram_user's own lookup is a
    # functional index over credentials->'telegram'->>'id' (auth/
    # service.py), which works identically regardless of how that key
    # got there.
    telegram_id = 900000 + (uuid.uuid4().int % 90000)
    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    updated_creds = dict(user.credentials or {})
    updated_creds["telegram"] = {
        "id": telegram_id,
        "username": None,
        "first_name": "Test",
        "last_name": "User",
        "photo_url": None,
        "language_code": "en",
    }
    user.set_jsonb("credentials", updated_creds)
    await db_session.commit()

    init_data = build_init_data(telegram_id=telegram_id, first_name="Test")
    resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mfa_required"] is True
    assert body["mfa_token"]
    assert body["session_token"] is None


@pytest.mark.asyncio
async def test_telegram_2fa_login_verify_session_tagged_telegram(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Completing a Telegram-originated 2FA login must tag the resulting
    session (and its audit row) auth_method="telegram", not "email".

    An adversarial review caught that create_mfa_pending_token() dropped
    which login path minted the pending token, so verify_2fa_login()
    hardcoded "email" for EVERY 2FA-completed login regardless of origin
    -- on a platform whose own code comments require every auth event to
    be correctly recorded for compliance, mislabeling a Telegram login's
    session/audit row as email is a real defect, not cosmetic. This test
    completes the flow test_telegram_login_also_honours_2fa above stops
    short of (it only proves the login STEP is gated, never calls
    login-verify), so the mislabel bug had nothing here to catch it.
    """
    password = "Password123!"
    _token, email, secret, _codes = await _enable_2fa(client, password=password)

    telegram_id = 900000 + (uuid.uuid4().int % 90000)
    user = (
        await db_session.execute(
            select(User).where(
                User.credentials["email"]["email"].as_string() == email
            )
        )
    ).scalar_one()
    updated_creds = dict(user.credentials or {})
    updated_creds["telegram"] = {
        "id": telegram_id,
        "username": None,
        "first_name": "Test",
        "last_name": "User",
        "photo_url": None,
        "language_code": "en",
    }
    user.set_jsonb("credentials", updated_creds)
    await db_session.commit()

    init_data = build_init_data(telegram_id=telegram_id, first_name="Test")
    login_resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data},
    )
    assert login_resp.status_code == 200, login_resp.text
    mfa_token = login_resp.json()["mfa_token"]

    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post(
        "/api/v1/auth/2fa/login-verify",
        json={"mfa_token": mfa_token, "code": code},
    )
    assert verify_resp.status_code == 200, verify_resp.text
    session_token = verify_resp.json()["session_token"]

    # The session this login-verify just created must self-report as
    # telegram, not the hardcoded "email" the bug produced.
    sessions_resp = await client.get(
        "/api/v1/auth/sessions", headers=auth_headers(session_token)
    )
    assert sessions_resp.status_code == 200, sessions_resp.text
    current = next(
        s for s in sessions_resp.json()["items"] if s["is_current"]
    )
    assert current["auth_method"] == "telegram"
