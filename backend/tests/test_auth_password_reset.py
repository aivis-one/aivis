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
# H34 ADDED (P-125):
#   6: Links sent before support changed the address are refused after
#      it (password_reset_link_invalidated), every one of them, and the
#      password does not move
#   7: The pair: after the change a link sent to the NEW address works
#   8: A token record that does not say where the link went is refused
#      like any dead token -- no fallback to the old record shape
#
# Both endpoints are UNAUTHENTICATED (see auth/service.py's "PASSWORD
# RESET" module note) -- no reset call in this file carries
# auth_headers(); the ones that do are other endpoints (logout, and the
# staff address change in 6-7).
#
# The request endpoint's fixed response means tests cannot read the
# token off the HTTP response (that is the whole point -- anti-
# enumeration). `capture_reset_email` reads it off the OUTBOX EVENT the
# service emits instead -- see that fixture for why the seam moved.
#
# Email prefix: "pwreset_" -- unique to this test file.
# =============================================================================

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from app.modules.auth.service import _PASSWORD_RESET_REDIS_PREFIX
from tests.helpers import (
    auth_headers,
    create_admin_user,
    login_user,
    register_user,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def capture_reset_email(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Capture the notification_request the service emits for a reset.

    WHAT THIS REPLACED, AND WHAT THE OLD VERSION WAS RIGHT ABOUT. It
    used to monkeypatch auth.service._send_password_reset_email -- the
    function that built an EmailMessage and handed it to core/email.py
    -- and record the (email, token) pair it was called with. That was
    the right seam while the product sent its own mail: it was the last
    point at which the token was in the product's hands.

    The product does not send mail any anymore. It emits a comms
    `notification_request` into the transactional outbox, and that row
    is now the last point at which the token is ours. So the fixture
    wraps emit_event instead. The REAL emit_event still runs underneath
    -- the row is written and validated (known event type, JSON-scalar
    payload, tz-aware expiry_at) -- and the wrapper only records the
    payload on the way past. The assertion the tests make therefore got
    stronger, not weaker: it used to be "the sender was called with
    this token", it is now "an event carrying this token reached the
    outbox in the right shape".

    WHY comms_configured IS PATCHED TOO, AND WHY HERE AND NOT ON
    settings. The emitters return early when this box has no comms
    address, which is the state of the test environment. Patching the
    name as auth.service sees it turns that gate off for the module
    under test and NOTHING else -- in particular it leaves
    core/comms_sync's own gate alone, so registering a user inside
    these tests still takes its no-op path instead of trying to reach a
    comms host that does not exist.

    Keys recorded: "token", "target_value" (the recipient's user id --
    the event carries no email address, comms resolves that from its
    own recipient record), "type", "expiry_at", and whether the data
    names a channel at all -- comms 3.0.0 refuses a request that does;
    the channel is comms-profile/types.yaml's.
    """
    from app.modules.auth import service as auth_service

    captured: dict = {}
    real_emit = auth_service.emit_event

    async def _capturing_emit(session, event_type, data):  # type: ignore[no-untyped-def]
        if data.get("type") == "auth.password_reset":
            captured["token"] = data["body"].rsplit("token=", 1)[-1].split("\n")[0]
            captured["target_value"] = data["target_value"]
            captured["type"] = data["type"]
            captured["names_a_channel"] = "channels" in data
            captured["expiry_at"] = data.get("expiry_at")
        return await real_emit(session, event_type, data)

    monkeypatch.setattr(auth_service, "comms_configured", lambda: True)
    monkeypatch.setattr(auth_service, "emit_event", _capturing_emit)
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
    # The event targets the user by id; it carries no address, because
    # comms resolves the address from its own recipient record.
    assert capture_reset_email["target_value"] == data["user"]["id"]
    # Until H23 this asserted channels == ["email"] on the event: right
    # while the request chose its channel. comms 3.0.0 takes the channel
    # from the profile and refuses a request that names one, so the
    # claim now is that the request names none (types.yaml routes the
    # type to email).
    assert capture_reset_email["names_a_channel"] is False
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

    Also confirms the internal branch actually happened (an event was
    emitted only for the real address) so this test is not accidentally
    passing because NEITHER branch does anything.
    """
    real_email = f"pwreset_real_{uuid.uuid4().hex[:12]}@example.com"
    fake_email = f"pwreset_ghost_{uuid.uuid4().hex[:12]}@example.com"
    real_user = await register_user(client, email=real_email)

    real_resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": real_email},
    )
    real_captured_target = capture_reset_email.get("target_value")
    capture_reset_email.clear()

    fake_resp = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": fake_email},
    )
    fake_captured_target = capture_reset_email.get("target_value")

    assert real_resp.status_code == fake_resp.status_code == 200
    assert real_resp.json() == fake_resp.json()

    # The internal branch DID differ -- proves the test exercises the
    # real "match found" vs "no match" code paths, not two no-ops. The
    # identity checked is the recipient id rather than the address: the
    # emitted event never carries an address.
    assert real_captured_target == real_user["user"]["id"]
    assert fake_captured_target is None


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


# ---------------------------------------------------------------------------
# 6-8: the address the link was sent to (H34 P-125)
# ---------------------------------------------------------------------------

_SUPPORT_REASON = "Old mailbox lost; identity checked by support."


async def _support_moves_address(
    client: AsyncClient, db_session: AsyncSession, user_id: str
) -> str:
    """Support changes the user's address the way the product does it --
    the staff endpoint behind change_user_email. Returns the new one."""
    _, admin_token = await create_admin_user(client, db_session)
    new_email = f"pwreset_moved_{uuid.uuid4().hex[:12]}@example.com"
    resp = await client.patch(
        f"/api/v1/staff/users/{user_id}/email",
        json={"email": new_email, "reason": _SUPPORT_REASON},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 204, resp.text
    return new_email


async def _confirm(client: AsyncClient, token: str, password: str):  # type: ignore[no-untyped-def]
    return await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": password},
    )


@pytest.mark.asyncio
async def test_links_sent_before_an_address_change_die_with_it(
    client: AsyncClient,
    db_session: AsyncSession,
    capture_reset_email: dict,
) -> None:
    """Two links reach the old mailbox; support then moves the account to
    a new address. Both links are refused with their own code, and the
    password is untouched -- the original one still logs in at the new
    address. A refused link is spent: offered again it is just dead.

    Before H34 the record named only the user, so whoever read the old
    mailbox could set a password for the rest of the 30 minutes."""
    old_email = f"pwreset_old_{uuid.uuid4().hex[:12]}@example.com"
    password = "OriginalPassword1"
    data = await register_user(client, email=old_email, password=password)

    await _request_reset(client, old_email)
    first_token = capture_reset_email["token"]
    await _request_reset(client, old_email)
    second_token = capture_reset_email["token"]
    assert first_token != second_token

    new_email = await _support_moves_address(
        client, db_session, data["user"]["id"]
    )

    for token in (first_token, second_token):
        resp = await _confirm(client, token, "TakenOverPassword9")
        assert resp.status_code == 400, resp.text
        assert resp.json()["error"] == "password_reset_link_invalidated"

    await login_user(client, email=new_email, password=password)

    again = await _confirm(client, first_token, "TakenOverPassword9")
    assert again.status_code == 400, again.text
    assert again.json()["error"] == "bad_request"


@pytest.mark.asyncio
async def test_a_link_to_the_new_address_works_after_the_change(
    client: AsyncClient,
    db_session: AsyncSession,
    capture_reset_email: dict,
) -> None:
    """The pair of the test above: the refusal is about WHERE the link
    went, not about the account having changed. A link requested after
    the change goes to the new address and sets the password."""
    old_email = f"pwreset_old_{uuid.uuid4().hex[:12]}@example.com"
    data = await register_user(client, email=old_email)
    new_email = await _support_moves_address(
        client, db_session, data["user"]["id"]
    )

    await _request_reset(client, new_email)
    resp = await _confirm(client, capture_reset_email["token"], "BrandNewPassword7")
    assert resp.status_code == 204, resp.text

    await login_user(client, email=new_email, password="BrandNewPassword7")


@pytest.mark.asyncio
async def test_a_record_without_the_address_is_refused(
    client: AsyncClient,
) -> None:
    """A record in the pre-H34 shape -- the user and nothing else -- is
    refused with the generic dead-token answer, not honoured: there is no
    fallback to the old shape ("no legacy"), because a link that cannot
    say where it went cannot pass the address check. The password does
    not move."""
    email = f"pwreset_shape_{uuid.uuid4().hex[:12]}@example.com"
    password = "OriginalPassword1"
    data = await register_user(client, email=email, password=password)

    token = f"h34-shape-{uuid.uuid4().hex}"
    await get_redis().set(
        f"{_PASSWORD_RESET_REDIS_PREFIX}{token}",
        json.dumps({"user_id": data["user"]["id"]}),
        ex=60,
    )

    resp = await _confirm(client, token, "TakenOverPassword9")
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "bad_request"

    await login_user(client, email=email, password=password)
