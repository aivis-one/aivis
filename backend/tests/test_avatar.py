# =============================================================================
# AIVIS.ONE Backend -- Avatar Tests (Sprint 3.2)
# =============================================================================
#
# Tests cover:
#   1:  Start avatar -> 200, returns session_token + avatar_session_id
#   2:  Avatar token authenticates as target user
#   3:  End avatar -> 204, session closed
#   4:  Get active avatar -> returns session info
#   5:  Get active avatar when none -> null
#   6:  Start avatar without avatar_mode permission -> 403
#   7:  Avatar into staff user -> 400
#   8:  Avatar into non-existent user -> 404
#   9:  Re-start avatar auto-closes previous session
#   10: Avatar guard blocks restricted operation in avatar mode
#   11: R49 -- create_withdrawal blocked in avatar mode (403)
#   12: R49 -- create_payment blocked in avatar mode (403): both the
#       invoice-creation and the TXID-submission surfaces
#   13: R49 -- create_installment blocked in avatar mode (403)
#   14: R49 -- modify_kyc (/kyc/submit) blocked in avatar mode (403)
#   15: R50 -- create_purchase blocked in avatar mode (403)
#   16: R50 -- route-walk: every restricted operation with a live
#       endpoint carries its forbid_avatar_* dependency (the guard
#       is self-checking: removing one from a route fails the suite)
#   17: 2026-08-17 -- with the switch OFF (the shipped default), a
#       restricted operation is NOT blocked in avatar mode
#   18: STAGE-III-FINDINGS.md #19 -- logout_all blocked in avatar mode
#   19: STAGE-III-FINDINGS.md #18 -- a Redis session carrying
#       avatar_session_id without avatar_staff_id is refused outright
#       (401), not silently treated as an ordinary session
#
# THE SWITCH, owner-ruled 2026-08-17 -- read this before editing tests 10-15.
#   settings.avatar_restrictions_enabled defaults to False, so an admin in
#   avatar mode may do everything. Tests 10-15 exist to prove the guard STILL
#   WORKS when the switch is on, so each one turns it on explicitly via the
#   avatar_restrictions_on fixture. They do NOT rely on a default -- and the
#   default they used to rely on is now the opposite of what they assert.
#   Test 17 is the other half: it pins the SHIPPED behaviour, and without it
#   the suite would prove only the state nobody currently runs in.
#
# Email prefix: "s32_" -- unique to this test file, cleaned up in fixture.
# =============================================================================

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
)


@pytest.fixture
def avatar_restrictions_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn the avatar restriction switch ON for the duration of one test.

    The shipped default is OFF (owner-ruled 2026-08-17). A guard test that
    asserts 403 must therefore set the switch itself; monkeypatch restores
    the real value afterwards, so no test leaks state into the next.
    """
    monkeypatch.setattr(settings, "avatar_restrictions_enabled", True)



async def _admin_token(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: create admin and return token."""
    _, token = await create_admin_user(
        client, db_session
    )
    return token


async def _investor_id_and_token(
    client: AsyncClient
) -> tuple[str, str]:
    """Helper: register investor, return (user_id, token)."""
    data = await register_user(client)
    return data["user"]["id"], data["session_token"]


# ---------------------------------------------------------------------------
# POST /staff/avatar/start
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_avatar(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Admin starts avatar -> 200, returns avatar_session_id + session_token."""
    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "avatar_session_id" in body
    assert "session_token" in body


@pytest.mark.asyncio
async def test_avatar_token_authenticates_as_target(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Avatar token loads target user via GET /users/me."""
    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    # Start avatar.
    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    avatar_token = resp.json()["session_token"]

    # Use avatar token to access /users/me -> should return investor.
    me_resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(avatar_token),
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["id"] == investor_id
    assert me_resp.json()["role"] == "investor"


# ---------------------------------------------------------------------------
# POST /staff/avatar/end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_end_avatar(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """End avatar -> 204, avatar token becomes invalid."""
    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    # Start avatar.
    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    avatar_token = resp.json()["session_token"]

    # End avatar using staff's original token.
    end_resp = await client.post(
        "/api/v1/staff/avatar/end",
        headers=auth_headers(admin_token),
    )
    assert end_resp.status_code == 204

    # Avatar token should no longer work.
    me_resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(avatar_token),
    )
    assert me_resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /staff/avatar/active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_avatar(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get active avatar session -> returns info."""
    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    # Start avatar.
    start_resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    avatar_session_id = start_resp.json()["avatar_session_id"]

    # Get active.
    resp = await client.get(
        "/api/v1/staff/avatar/active",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == avatar_session_id
    assert body["target_user_id"] == investor_id
    assert body["status"] == "active"


@pytest.mark.asyncio
async def test_get_active_avatar_none(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Get active avatar when none -> null."""
    admin_token = await _admin_token(client, db_session)

    resp = await client.get(
        "/api/v1/staff/avatar/active",
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json() is None


# ---------------------------------------------------------------------------
# Permission + validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_avatar_without_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Staff without avatar_mode permission -> 403."""
    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    # Create regular staff, remove avatar_mode. The email is held in a
    # local so the later login_user call hits the same account.
    noavatar_email = f"noavatar_{uuid.uuid4().hex[:12]}@example.com"
    regular_data = await register_user(
        client, email=noavatar_email
    )
    resp = await client.post(
        "/api/v1/staff/users",
        json={"user_id": regular_data["user"]["id"]},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201
    profile_id = resp.json()["id"]

    # Remove avatar_mode permission.
    await client.patch(
        f"/api/v1/staff/users/{profile_id}/permissions",
        json={"avatar_mode": False},
        headers=auth_headers(admin_token),
    )

    # Re-login as regular staff.
    from tests.helpers import login_user
    login_data = await login_user(
        client, email=noavatar_email
    )
    regular_token = login_data["session_token"]

    # Try to start avatar -> 403.
    resp2 = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(regular_token),
    )
    assert resp2.status_code == 403


@pytest.mark.asyncio
async def test_avatar_into_staff_fails(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Avatar into another staff user -> 400."""
    admin_token = await _admin_token(client, db_session)

    # Create another staff.
    other_data = await register_user(
        client
    )
    await client.post(
        "/api/v1/staff/users",
        json={"user_id": other_data["user"]["id"]},
        headers=auth_headers(admin_token),
    )

    # Try to avatar into them.
    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": other_data["user"]["id"]},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_avatar_nonexistent_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Avatar into non-existent user -> 404."""
    from uuid import uuid4

    admin_token = await _admin_token(client, db_session)

    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": str(uuid4())},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auto-close previous avatar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_avatar_closes_previous(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Starting new avatar auto-closes the previous one."""
    admin_token = await _admin_token(client, db_session)
    inv1_id, _ = await _investor_id_and_token(client)
    inv2_id, _ = await _investor_id_and_token(client)

    # Start avatar for inv1.
    resp1 = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": inv1_id},
        headers=auth_headers(admin_token),
    )
    token1 = resp1.json()["session_token"]

    # Start avatar for inv2 -> auto-closes inv1.
    resp2 = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": inv2_id},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 200
    token2 = resp2.json()["session_token"]

    # Token1 should be invalid.
    me1 = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token1),
    )
    assert me1.status_code == 401

    # Token2 should work and return inv2.
    me2 = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token2),
    )
    assert me2.status_code == 200
    assert me2.json()["id"] == inv2_id


# ---------------------------------------------------------------------------
# Avatar guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_avatar_guard_blocks_in_avatar_mode(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """forbid_avatar dependency blocks restricted operations (R49: was
    the require_not_avatar decorator; this test pins the migration).

    Uses sign_document as a restricted operation (in RESTRICTED_OPERATIONS).
    Avatar token should get 403 when trying to sign.
    """
    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    # Start avatar.
    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    avatar_token = resp.json()["session_token"]

    # Create a document to sign (using admin token).
    # version is randomized: seed_documents.py owns versions 1..N for the
    # real legal docs, and prior test runs leave their own (privacy_policy,
    # 99, en) row behind. uq_documents_type_version_language collides on
    # any reuse, so we pick a random version far above the seed range.
    # 7 hex digits -> max 268M, safely inside Integer (int32) range.
    doc_resp = await client.post(
        "/api/v1/staff/documents",
        json={
            "type": "privacy_policy",
            "title": "Test PP",
            "language": "en",
            "version": int(uuid.uuid4().hex[:7], 16),
        },
        headers=auth_headers(admin_token),
    )
    assert doc_resp.status_code == 201
    doc_id = doc_resp.json()["id"]

    # Publish it.
    await client.patch(
        f"/api/v1/staff/documents/{doc_id}",
        json={"status": "active"},
        headers=auth_headers(admin_token),
    )

    # Try to sign with avatar token -> should be blocked by avatar_guard.
    sign_resp = await client.post(
        f"/api/v1/documents/{doc_id}/sign",
        headers=auth_headers(avatar_token),
    )
    assert sign_resp.status_code == 403
    assert "avatar" in sign_resp.json()["message"].lower()


# ---------------------------------------------------------------------------
# Avatar guard -- R49: the four financial/KYC operations
# ---------------------------------------------------------------------------


async def _avatar_token_for_fresh_investor(
    client: AsyncClient, db_session: AsyncSession
) -> str:
    """Helper: admin avatars into a fresh investor, returns avatar token."""
    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200
    return resp.json()["session_token"]


@pytest.mark.asyncio
async def test_avatar_blocked_create_withdrawal(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """R49: POST /withdrawals in avatar mode -> 403 (forbid_avatar)."""
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/withdrawals",
        json={"amount_cents": 1000},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_create_payment(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """R49: POST /payments/invoices in avatar mode -> 403.

    RETARGETED, NOT WEAKENED. The old assertion aimed at
    POST /payments/crypto-address and was right about the rule: staff
    in avatar mode must not initiate a deposit on somebody's behalf.
    What ended it was the route, not the rule -- the stub deposit-address
    contour was removed in H7 and invoice creation took its place as the
    user-facing payment-creation surface. Left pointing at the old path
    this test would have gone green on a 404 while the guard it exists
    for went unchecked.

    The 403 must arrive before any call to the payments service, which
    is why no service is configured in tests and this still passes: the
    avatar guard is a route dependency and runs ahead of the handler.
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/payments/invoices",
        json={"network": "USDT-TRC20", "amount_cents": 10000},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_submit_txid(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """R49: POST /payments/invoices/{id}/txid in avatar mode -> 403.

    NEW SURFACE, SAME RULE. Claiming a transfer by submitting its hash
    is the second half of initiating a deposit, and it did not exist
    when R49 was written. A guard on creation alone would let staff in
    avatar mode finish a deposit somebody else started.

    The invoice id is a random uuid on purpose: a 403 that depended on
    the invoice existing would be a weaker assertion, because it could
    not tell "the guard ran" from "the lookup failed".
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        f"/api/v1/payments/invoices/{uuid.uuid4()}/txid",
        json={"txid": "0x" + "a" * 64},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_create_installment(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """R49: POST /products/{id}/installment in avatar mode -> 403.

    The guard dependency fires before the handler -- the random
    product_id never reaches the 404 path.
    """
    from uuid import uuid4

    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        f"/api/v1/products/{uuid4()}/installment",
        json={"product_installment_id": str(uuid4())},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_modify_kyc(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """R49: POST /kyc/submit in avatar mode -> 403.

    /kyc/advance is intentionally NOT guarded (idempotent onboarding
    unstick helper -- staff legitimately use it via avatar).
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/kyc/submit",
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_create_purchase(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """R50: POST /products/{id}/purchase in avatar mode -> 403.

    Boss decision (R50): spending the user's balance is exactly the
    threat class the avatar guard exists for -- reversibility via the
    R-2.2 chargeback is cleanup, not prevention. The guard dependency
    fires before the handler, so the random product_id never reaches
    the 404 path.
    """
    from uuid import uuid4

    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        f"/api/v1/products/{uuid4()}/purchase",
        json={},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_logout_all(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """STAGE-III-FINDINGS.md #19: POST /auth/logout-all in avatar mode -> 403.

    Before this guard, an avatar could end every session the REAL
    owner holds on every device while its own avatar session survived
    -- a disruption vector, not a money-path one, but real and
    reachable with no legitimate avatar-mode use case.
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/auth/logout-all",
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_email_change_request(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """TASK-38: POST /users/me/email-change in avatar mode -> 403.

    An avatar must not be able to move the account's login email onto
    an address only it controls. The guard fires as a route dependency
    ahead of the handler, so a bogus current_password in the body
    (which the guard never inspects) does not matter here -- same
    pattern as test_avatar_blocked_create_withdrawal's `{"amount_cents":
    1000}` body never reaching the withdrawal service.
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/users/me/email-change",
        json={
            "current_password": "whatever-the-avatar-does-not-know-it",
            "new_email": f"hijack_{uuid.uuid4().hex[:12]}@example.com",
        },
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_deactivate_account(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """TASK-38: POST /users/me/deactivate in avatar mode -> 403.

    An avatar must not be able to deactivate the account it is
    impersonating.
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/users/me/deactivate",
        json={"current_password": "whatever-the-avatar-does-not-know-it"},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_revoke_session(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """TASK-38: DELETE /auth/sessions/{id} in avatar mode -> 403.

    An adversarial review of the active-sessions build caught that the
    self-checking guard-walk test (which only confirms the dependency
    NAME is wired on the route) was the only coverage for this endpoint
    in avatar mode -- every OTHER forbid_avatar-gated endpoint has a
    real end-to-end test like this one, this was the gap.

    Uses the investor's OWN real session_id (fetched via GET
    /auth/sessions with their own token, before avataring in) rather
    than a placeholder id -- proves a genuine target session survives
    the blocked attempt, not merely that a nonsense id gets rejected
    before the handler runs.
    """
    admin_token = await _admin_token(client, db_session)
    investor_id, investor_token = await _investor_id_and_token(client)

    sessions_resp = await client.get(
        "/api/v1/auth/sessions",
        headers=auth_headers(investor_token),
    )
    assert sessions_resp.status_code == 200
    session_id = sessions_resp.json()["items"][0]["session_id"]

    start_resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert start_resp.status_code == 200
    avatar_token = start_resp.json()["session_token"]

    resp = await client.delete(
        f"/api/v1/auth/sessions/{session_id}",
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()

    # The targeted session must genuinely survive -- the guard blocked
    # the whole request, not merely returned an error status while the
    # revoke happened anyway.
    still_there = await client.get(
        "/api/v1/auth/sessions",
        headers=auth_headers(investor_token),
    )
    assert any(
        s["session_id"] == session_id for s in still_there.json()["items"]
    )


@pytest.mark.asyncio
async def test_avatar_blocked_mute_notifications(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """TASK-38: PATCH /notifications/preferences in avatar mode -> 403.

    An adversarial review of the notification-preferences build caught
    that its first draft tested only "does this move money or
    identity" and missed the threat class logout_all/revoke_session
    guard for: a mutation that PERSISTS past the avatar session and
    suppresses the channel the real owner would use to notice
    unauthorized activity on their money/identity. Confirms both the
    403 AND that a targeted category genuinely stays unmuted -- the
    guard blocked the whole request, not merely returned an error
    while the write happened anyway.
    """
    admin_token = await _admin_token(client, db_session)
    investor_id, investor_token = await _investor_id_and_token(client)

    before = await client.get(
        "/api/v1/notifications/preferences",
        headers=auth_headers(investor_token),
    )
    assert before.status_code == 200
    categories = before.json()["categories"]
    assert categories, "fixture assumption: at least one category exists"
    target_category = next(iter(categories))
    assert categories[target_category] is True, (
        "fixture assumption: target category starts enabled"
    )

    start_resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert start_resp.status_code == 200
    avatar_token = start_resp.json()["session_token"]

    resp = await client.patch(
        "/api/v1/notifications/preferences",
        json={"categories": {target_category: False}},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()

    after = await client.get(
        "/api/v1/notifications/preferences",
        headers=auth_headers(investor_token),
    )
    assert after.json()["categories"][target_category] is True


@pytest.mark.asyncio
async def test_avatar_blocked_update_profile(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """TASK-38: PATCH /users/me in avatar mode -> 403.

    Navigator-30's review of the batch caught this endpoint as the one
    identity-mutating route left ungated -- it writes profile.country/
    profile.phone, fields this codebase's own users/router.py header
    comment calls AML/KYC-significant. Confirms both the 403 AND that
    the target's profile genuinely stays unchanged, not just that the
    request itself was refused.
    """
    admin_token = await _admin_token(client, db_session)
    investor_id, investor_token = await _investor_id_and_token(client)

    before = await client.get(
        "/api/v1/users/me", headers=auth_headers(investor_token)
    )
    assert before.status_code == 200
    original_country = before.json().get("profile", {}).get("country")

    start_resp = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert start_resp.status_code == 200
    avatar_token = start_resp.json()["session_token"]

    resp = await client.patch(
        "/api/v1/users/me",
        json={"profile": {"country": "ZZ-avatar-should-not-land"}},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()

    after = await client.get(
        "/api/v1/users/me", headers=auth_headers(investor_token)
    )
    assert after.json().get("profile", {}).get("country") == original_country


@pytest.mark.asyncio
async def test_avatar_blocked_2fa_setup(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """TASK-38: POST /auth/2fa/setup in avatar mode -> 403.

    An avatar must not be able to plant a TOTP secret on the real
    owner's account that only the avatar has ever seen -- see
    avatar_guard.py's manage_2fa note. A bogus current_password in the
    body never matters here: the guard is a route dependency and fires
    before the handler even parses it, same pattern as every other
    forbid_avatar test in this file.
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/auth/2fa/setup",
        json={"current_password": "whatever-the-avatar-does-not-know-it"},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_avatar_blocked_2fa_disable(
    client: AsyncClient,
    db_session: AsyncSession,
    avatar_restrictions_on: None,
) -> None:
    """TASK-38: POST /auth/2fa/disable in avatar mode -> 403.

    Same reasoning as test_avatar_blocked_2fa_setup, opposite
    direction: an avatar must not be able to strip a security control
    the real owner deliberately turned on. Uses a fresh investor with
    no 2FA configured at all -- the guard fires before the handler ever
    reaches disable_totp()'s "not enabled" check, so the account's real
    2FA state is irrelevant to this test.
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/auth/2fa/disable",
        json={
            "current_password": "whatever-the-avatar-does-not-know-it",
            "code": "000000",
        },
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 403
    assert "avatar" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_shipped_default_leaves_avatar_restrictions_off() -> None:
    """2026-08-17, owner-ruled: the switch ships OFF.

    Pinned on its own so that flipping the default is a visible act with a
    named failure, not a quiet change of behaviour. Update the ruling and
    this assertion together, never one of them alone.
    """
    assert settings.avatar_restrictions_enabled is False


@pytest.mark.asyncio
async def test_avatar_guard_follows_the_switch_both_ways(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ONE request, ONE token, ONE route -- only the switch differs.

    This is the strongest form available, because the two outcomes are
    separated by nothing except the setting under test. Anything else that
    could explain the difference is held identical by construction.

    ⚠ ITS FIRST DRAFT ASSERTED 404 AND FAILED AT 400, and the reason is
    worth keeping: it assumed an unknown product_id would fall through to a
    404 lookup, but the endpoint validates the request BODY first, and this
    test posts `{}` -- the same empty body the blocked-case test posts,
    which never reaches validation because the guard short-circuits it.
    So the handler's own status code was never the point and guessing it
    was the error. What the test actually needs to prove is narrower and
    exact: THE GUARD DID NOT FIRE. 403-with-the-guard's-own-message is that
    signal, and its absence is the assertion.
    """
    from uuid import uuid4

    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)
    product_id = uuid4()

    async def attempt():
        return await client.post(
            f"/api/v1/products/{product_id}/purchase",
            json={},
            headers=auth_headers(avatar_token),
        )

    # -- switch ON: the guard fires --
    monkeypatch.setattr(settings, "avatar_restrictions_enabled", True)
    blocked = await attempt()
    assert blocked.status_code == 403, (
        f"with restrictions ON the guard must block; got {blocked.status_code}"
    )
    assert "avatar" in blocked.json()["message"].lower()

    # -- switch OFF (the shipped default): the guard does not fire --
    monkeypatch.setattr(settings, "avatar_restrictions_enabled", False)
    allowed = await attempt()
    assert allowed.status_code != 403, (
        f"with restrictions OFF the guard must NOT block; got "
        f"{allowed.status_code}. The owner ruled avatar mode fully open "
        f"2026-08-17 (decision 76)."
    )
    assert "not allowed in avatar mode" not in allowed.text, (
        "the guard's own refusal reached the client while the switch is off"
    )


@pytest.mark.asyncio
async def test_avatar_may_rewrite_payout_details(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """STAGE-III finding 17, owner-ruled 2026-08-17: an avatar CAN rewrite
    the target's payout destination, and that is now ACCEPTED behaviour.

    This test does not defend the behaviour -- it PINS it. The finding is
    real and was traced end to end: the value written here is snapshotted
    into the withdrawal at creation and is what a payment_review operator
    reads and pays to by hand. The owner ruled it acceptable for now because
    he is testing the whole product through the admin account, and named his
    own trigger for revisiting it: real users and real money.

    So the point of the test is that the day the ruling is reversed, this
    test fails and says so, instead of the behaviour changing under a plan
    that still assumes it. PUT /me/payout-details carries no forbid_avatar
    guard at all -- it is not one of the six -- so this passes whether the
    switch is on or off. That is deliberate: it pins the ROUTE's exposure,
    which the switch does not currently cover.
    """
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    new_destination = {"method": "crypto", "address": "TAvatarRewroteThis"}
    resp = await client.put(
        "/api/v1/users/me/payout-details",
        json={"payout_details": new_destination},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 200, (
        f"expected the avatar to be able to rewrite payout details "
        f"(owner-ruled 2026-08-17); got {resp.status_code}"
    )
    assert resp.json()["payout_details"] == new_destination

    # And it really landed on the TARGET user, not somewhere else.
    read_back = await client.get(
        "/api/v1/users/me/payout-details",
        headers=auth_headers(avatar_token),
    )
    assert read_back.status_code == 200
    assert read_back.json()["payout_details"] == new_destination


# ---------------------------------------------------------------------------
# TASK-22 / finding 16 -- the ENDED-while-Redis-alive state (2026-08-17)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_avatar_token_refused_when_row_ended_but_redis_key_lives(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An AvatarSession row set to ENDED must revoke the token immediately,
    even though its Redis key is untouched and unexpired.

    THIS IS THE STATE TASK-6 4.3 WAS BUILT FOR AND NOTHING COVERED IT.
    Measured 2026-08-16: `_check_avatar_still_active` had ZERO hits across
    the whole test suite, control fired -- the very mechanism decision 64
    added, with no test on it. Before 4.3, Redis was sole authority, so
    ending a session by any route other than the /end endpoint's own
    Redis-delete path did not actually revoke anything.

    The test deliberately does NOT call /staff/avatar/end: that path deletes
    the Redis key, which would make the token fail for the OLD reason and
    prove nothing about the DB check. It ends the row directly, leaving the
    key alive -- which is exactly the shape an admin-side revocation, a
    background expiry, or a support action produces.

    dependencies.py:125 is the line under test; UnauthorizedError -> 401.
    """
    from sqlalchemy import select

    from app.modules.staff.models import AvatarSession, AvatarSessionStatus

    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    start = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert start.status_code == 200
    avatar_token = start.json()["session_token"]
    avatar_session_id = start.json()["avatar_session_id"]

    # CONTROL, and it is the half that makes the assertion below mean
    # anything: the token works right now. Without it, a token that was
    # never valid would produce the same 401 and the test would pass for
    # the wrong reason.
    alive = await client.get("/api/v1/users/me", headers=auth_headers(avatar_token))
    assert alive.status_code == 200, (
        "the avatar token must work BEFORE the row is ended -- otherwise "
        "the 401 below proves nothing"
    )
    assert alive.json()["id"] == investor_id

    # End the ROW only. Redis is left exactly as it was.
    row = (
        await db_session.execute(
            select(AvatarSession).where(AvatarSession.id == uuid.UUID(avatar_session_id))
        )
    ).scalar_one()
    row.status = AvatarSessionStatus.ENDED
    await db_session.commit()

    dead = await client.get("/api/v1/users/me", headers=auth_headers(avatar_token))
    assert dead.status_code == 401, (
        f"an ENDED AvatarSession row must revoke the token on the next "
        f"request regardless of Redis; got {dead.status_code}"
    )


# ---------------------------------------------------------------------------
# STAGE-III-FINDINGS.md #18 -- the partial avatar-key state, 2026-08-27
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_avatar_session_missing_staff_id_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A Redis session carrying avatar_session_id WITHOUT avatar_staff_id
    must be refused outright (401), not silently treated as an ordinary
    session.

    Normal code always writes both keys together in one json.dumps blob
    (avatar_service.py's start_avatar) -- this state is reachable only
    from outside this pipeline (an ops script, a restored backup).
    Before dependencies.py's fail-closed branch, the binder's `if
    avatar_session_id and avatar_staff_id:` silently skipped binding when
    exactly one was present, so the request fell through as an ordinary
    user: none of avatar_guard.py's forbid_avatar restrictions applied,
    and record_audit() would have attributed the action to this user as
    their own rather than to any staff member.
    """
    import json

    from app.core.redis import get_redis

    admin_token = await _admin_token(client, db_session)
    investor_id, _ = await _investor_id_and_token(client)

    start = await client.post(
        "/api/v1/staff/avatar/start",
        json={"target_user_id": investor_id},
        headers=auth_headers(admin_token),
    )
    assert start.status_code == 200
    avatar_token = start.json()["session_token"]

    # CONTROL: the token works before the tamper, so the 401 below proves
    # the tamper was the cause, not a broken token.
    alive = await client.get("/api/v1/users/me", headers=auth_headers(avatar_token))
    assert alive.status_code == 200, (
        "the avatar token must work BEFORE the tamper -- otherwise the "
        "401 below proves nothing"
    )

    # Tamper: strip avatar_staff_id, leaving avatar_session_id alone --
    # exactly the partial state finding #18 describes. TTL preserved via
    # KEEPTTL so this isn't mistaken for testing plain expiry.
    redis = get_redis()
    session_key = f"session:{avatar_token}"
    raw = await redis.get(session_key)
    assert raw is not None, "the session key must exist to tamper with it"
    data = json.loads(raw)
    assert "avatar_staff_id" in data, "sanity: the key we're about to strip must be present"
    del data["avatar_staff_id"]
    await redis.set(session_key, json.dumps(data), keepttl=True)

    tampered = await client.get("/api/v1/users/me", headers=auth_headers(avatar_token))
    assert tampered.status_code == 401, (
        f"a session carrying avatar_session_id without avatar_staff_id must "
        f"be refused outright, not treated as an ordinary session; "
        f"got {tampered.status_code}"
    )


def test_every_restricted_operation_endpoint_carries_guard() -> None:
    """R50: the avatar guard is self-checking (reviewer R50-3.1).

    Walks app.routes and asserts every restricted operation with a
    live endpoint carries its forbid_avatar_* dependency. Removing a
    guard from a route -- or adding a new endpoint for a restricted
    operation without wiring the guard -- fails this test.

    Operations without live endpoints (change_password,
    access_staff_shell) are intentionally absent from the expected set;
    extend it when their endpoints appear. logout_all
    (STAGE-III-FINDINGS.md #19) was added to the expected set the same
    day its guard was wired, not left for a later pass -- change_email,
    delete_account, and revoke_session (TASK-38, users/router.py and
    auth/router.py DELETE /sessions/{id}) follow the same rule: added
    here the same change that wired their guards.

    The walk is recursive: since FastAPI 0.137 include_router no longer
    flattens a sub-router's routes into app.routes -- it inserts a lazy
    _IncludedRouter wrapper that keeps them in .original_router.routes.
    Descending through that wrapper (duck-typed on its presence) keeps
    the check working on both the flat (< 0.137) and wrapped (>= 0.137)
    representations. Fail-closed is preserved: dropping a guard removes
    the dependency from its route's dependant, so the expected set can
    no longer be satisfied and the test fails.
    """
    from app.main import app
    from starlette.routing import BaseRoute

    guarded: set[str] = set()

    def collect(routes: list[BaseRoute]) -> None:
        for route in routes:
            # FastAPI >= 0.137: a sub-router's routes live behind a lazy
            # _IncludedRouter wrapper rather than flattened in place.
            original = getattr(route, "original_router", None)
            if original is not None:
                collect(original.routes)
                continue
            dependant = getattr(route, "dependant", None)
            if dependant is None:
                continue
            for dep in dependant.dependencies:
                name = getattr(dep.call, "__name__", "")
                if name.startswith("forbid_avatar_"):
                    guarded.add(name)

    collect(app.routes)

    expected = {
        "forbid_avatar_create_withdrawal",
        "forbid_avatar_create_payment",
        "forbid_avatar_create_installment",
        "forbid_avatar_create_purchase",
        "forbid_avatar_modify_kyc",
        "forbid_avatar_sign_document",
        "forbid_avatar_logout_all",
        "forbid_avatar_change_email",
        "forbid_avatar_delete_account",
        "forbid_avatar_revoke_session",
        "forbid_avatar_mute_notifications",
        "forbid_avatar_manage_2fa",
        "forbid_avatar_update_profile",
    }
    missing = expected - guarded
    assert not missing, (
        f"restricted operations without a wired forbid_avatar guard: "
        f"{sorted(missing)}"
    )
