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
#   12: R49 -- create_payment (crypto-address) blocked in avatar mode (403)
#   13: R49 -- create_installment blocked in avatar mode (403)
#   14: R49 -- modify_kyc (/kyc/submit) blocked in avatar mode (403)
#   15: R50 -- create_purchase blocked in avatar mode (403)
#   16: R50 -- route-walk: every restricted operation with a live
#       endpoint carries its forbid_avatar_* dependency (the guard
#       is self-checking: removing one from a route fails the suite)
#   17: 2026-08-17 -- with the switch OFF (the shipped default), a
#       restricted operation is NOT blocked in avatar mode
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
    """R49: POST /payments/crypto-address in avatar mode -> 403."""
    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        "/api/v1/payments/crypto-address",
        json={"network": "TRC20"},
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
async def test_avatar_allowed_when_restrictions_switched_off(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """2026-08-17, owner-ruled: with the switch OFF -- the SHIPPED default --
    a restricted operation is NOT blocked in avatar mode.

    Deliberately the SAME route as test_avatar_blocked_create_purchase, and
    the pair is the whole point:
      switch ON  -> 403, the guard fires before the handler;
      switch OFF -> 404, the request reaches the handler and the random
                    product_id is simply not found.
    A 404 here therefore proves the guard did NOT fire -- it is not a weaker
    assertion than a 200, it is a sharper one, because the guard's own
    docstring is that it short-circuits before the handler is ever reached.

    This test takes NO avatar_restrictions_on fixture on purpose. It is the
    one test in this file that runs against the real shipped default, and if
    someone flips that default back the failure lands here, loudly, instead
    of the suite silently proving a configuration nobody runs.
    """
    from uuid import uuid4

    assert settings.avatar_restrictions_enabled is False, (
        "the shipped default changed -- this test pins it, so update the "
        "ruling and this assertion together, never one of them alone"
    )

    avatar_token = await _avatar_token_for_fresh_investor(client, db_session)

    resp = await client.post(
        f"/api/v1/products/{uuid4()}/purchase",
        json={},
        headers=auth_headers(avatar_token),
    )
    assert resp.status_code == 404, (
        f"expected the handler to be reached (404 for an unknown product); "
        f"got {resp.status_code} -- a 403 here means the avatar guard fired "
        f"while the restriction switch is off"
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


def test_every_restricted_operation_endpoint_carries_guard() -> None:
    """R50: the avatar guard is self-checking (reviewer R50-3.1).

    Walks app.routes and asserts every restricted operation with a
    live endpoint carries its forbid_avatar_* dependency. Removing a
    guard from a route -- or adding a new endpoint for a restricted
    operation without wiring the guard -- fails this test.

    Operations without live endpoints (change_password, change_email,
    delete_account, access_staff_shell) are intentionally absent from
    the expected set; extend it when their endpoints appear.

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
    }
    missing = expected - guarded
    assert not missing, (
        f"restricted operations without a wired forbid_avatar guard: "
        f"{sorted(missing)}"
    )
