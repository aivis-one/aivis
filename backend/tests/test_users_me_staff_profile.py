# =============================================================================
# CBSHOME Backend -- Users /me staff_profile Tests (iter 2.6c B6)
# =============================================================================
#
# HTTP-level coverage for the staff_profile field newly exposed on
# UserResponse from GET /api/v1/users/me.
#
# Tests cover:
#   1: investor /me  -> staff_profile is null
#   2: admin    /me  -> staff_profile populated; permissions dict has
#                       all DEFAULT_STAFF_PERMISSIONS keys, all True
#                       (admin = every key True)
#   3: plain staff /me -> staff_profile populated; permissions match
#                         the DEFAULT_STAFF_PERMISSIONS baseline (i.e.
#                         translation_edit=False, the rest True)
#
# Why three tests instead of two:
#   Admin vs plain staff exercises the same code path but verifies
#   that effective permissions reflect the per-staff overrides AND
#   the merge with defaults. Without the third test, a regression
#   where every staff response carries admin permissions would slip
#   through silently.
#
# Robustness:
#   Each test creates its own user (UUID-suffixed via the helpers'
#   defaults) so the shared dev DB has no cross-test bleed.
# =============================================================================

import pytest
from app.modules.staff.constants import DEFAULT_STAFF_PERMISSIONS
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import (
    auth_headers,
    create_admin_user,
    create_staff_user,
    register_user,
)


# ---------------------------------------------------------------------------
# 1: investor -- staff_profile is null
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_investor_has_no_staff_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A freshly registered investor calls GET /me and gets
    `staff_profile: null`. The field exists on UserResponse (so the
    frontend can read it unconditionally) but is null for non-staff.
    """
    inv = await register_user(client)
    token = inv["session_token"]

    resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # The role should be investor by default after register.
    # We don't strictly need to assert it -- the staff_profile=null
    # check is sufficient -- but it documents the precondition.
    assert body.get("role") == "investor"
    assert body.get("staff_profile") is None


# ---------------------------------------------------------------------------
# 2: admin -- staff_profile.permissions is the all-True matrix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_admin_staff_profile_all_permissions_true(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_admin_user flips every permission key to True so
    is_admin() returns True. /me must surface that on staff_profile.

    Contract checked:
      * staff_profile is a dict (not None).
      * permissions is a dict whose keys exactly match
        DEFAULT_STAFF_PERMISSIONS (admin = full coverage of the
        canonical key set).
      * every value is True.

    We assert the key set with `==` rather than `>=` because the
    effective dict comes from get_effective_permissions(profile),
    which merges with DEFAULT_STAFF_PERMISSIONS -- the result has
    exactly that key set even if the stored overrides are sparse.
    """
    user, token = await create_admin_user(client, db_session)

    resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body.get("role") == "staff"
    sp = body.get("staff_profile")
    assert sp is not None, (
        f"admin /me must surface staff_profile; body keys: "
        f"{list(body.keys())}"
    )

    # Shape: id, user_id, permissions, is_active, created_at.
    assert sp["user_id"] == str(user.id)
    assert sp["is_active"] is True
    assert isinstance(sp["permissions"], dict)

    perms = sp["permissions"]
    expected_keys = set(DEFAULT_STAFF_PERMISSIONS.keys())
    assert set(perms.keys()) == expected_keys, (
        f"permissions key set mismatch. "
        f"missing: {expected_keys - set(perms.keys())}, "
        f"extra: {set(perms.keys()) - expected_keys}"
    )
    assert all(isinstance(v, bool) for v in perms.values())
    assert all(v is True for v in perms.values()), (
        f"admin must have every permission True; got: {perms}"
    )


# ---------------------------------------------------------------------------
# 3: plain staff -- staff_profile.permissions matches the defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_plain_staff_staff_profile_matches_defaults(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """create_staff_user stores DEFAULT_STAFF_PERMISSIONS as overrides.
    Merging defaults with itself is idempotent, so the effective dict
    must equal DEFAULT_STAFF_PERMISSIONS verbatim.

    This guards against two regressions in one shot:
      * If build_user_response forgot to call get_effective_permissions
        and returned raw overrides, we'd still see the right value
        here -- but test 2 (admin) would still pass because admin
        stores the full all-True dict directly. The contrast between
        admin and plain staff makes the call-or-skip behaviour visible.
      * If the merge accidentally OR'd defaults with the override
        (taking True wherever defaults had True), translation_edit
        (default False) would flip to True for plain staff. Asserting
        exact-equality with DEFAULT_STAFF_PERMISSIONS catches that.
    """
    user, token = await create_staff_user(client, db_session)

    resp = await client.get(
        "/api/v1/users/me",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body.get("role") == "staff"
    sp = body.get("staff_profile")
    assert sp is not None

    assert sp["user_id"] == str(user.id)
    assert sp["is_active"] is True
    # Exact-equality on the dict, not just key membership: catches a
    # broken merge that would silently change a False to True.
    assert sp["permissions"] == dict(DEFAULT_STAFF_PERMISSIONS), (
        f"plain staff effective permissions must equal the defaults; "
        f"got: {sp['permissions']}"
    )
