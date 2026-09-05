# =============================================================================
# AIVIS.ONE Backend -- KYC Gate Tests (H10)
# =============================================================================
#
# The gate refuses an unverified investor everywhere outside a named
# list. These tests measure three separate things, and the third is the
# one that keeps the other two honest:
#
#   1. Every exempt route is actually reachable without verification,
#      one parametrised case per route -- and a non-exempt route is
#      refused. WITHOUT THE SECOND HALF the first would pass just as
#      well against a gate that was never wired up at all.
#   2. The refusal carries a code the client can act on, one per state.
#   3. The exempt list matches the live route table IN BOTH DIRECTIONS:
#      no entry naming a route that no longer exists or never needed a
#      session, and no session-requiring route in the reviewed modules
#      left undecided.
#
# MUTATIONS THIS FILE IS BUILT TO CATCH (run by hand, all three go red):
#   * remove Depends(enforce_kyc_gate) from main.py
#       -> every test in "the gate actually refuses" section fails
#   * add a gated path to KYC_GATE_EXEMPT_ROUTES
#       -> test_a_route_outside_the_list_is_refused fails
#   * delete an entry from KYC_GATE_EXEMPT_ROUTES
#       -> that route's parametrised case fails, plus the walk
#   * rename a route without updating the list
#       -> test_every_exempt_entry_names_a_live_session_route fails
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient

from app.core.database import get_session_factory
from app.main import app
from app.modules.auth.dependencies import get_current_user, get_current_user_write
from app.modules.kyc.gate import (
    KYC_GATE_EXEMPT_ROUTES,
    KYC_GATE_GATED_BY_DESIGN,
    KYC_GATE_REVIEWED_PREFIXES,
    is_gate_exempt_role,
)
from app.modules.users.models import KYCStatus, User, UserRole
from sqlalchemy import select
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
    submit_kyc_application,
)

_AUTH_DEPS = {get_current_user, get_current_user_write}


# ---------------------------------------------------------------------------
# Live route table -- the source, not a re-parse of the source code
# ---------------------------------------------------------------------------


def _collect(routes, live: set, session_required: set) -> None:
    """Walk app.routes, descending into lazily-included routers.

    FastAPI stopped flattening include_router: app.routes holds
    _IncludedRouter placeholders, and a flat loop over it sees three
    routes instead of a hundred and eighty-six -- every assertion below
    would pass while measuring nothing. Same descent as test_avatar.py.
    """
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            _collect(inner.routes, live, session_required)
            continue
        dependant = getattr(route, "dependant", None)
        if dependant is None or not getattr(route, "methods", None):
            continue
        needs_session = any(d.call in _AUTH_DEPS for d in dependant.dependencies)
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            live.add((method, route.path))
            if needs_session:
                session_required.add((method, route.path))


def _route_sets() -> tuple[set, set]:
    live: set = set()
    session_required: set = set()
    _collect(app.routes, live, session_required)
    # A flat walk returns almost nothing; if the descent above ever
    # breaks, fail here rather than passing everything downstream.
    assert len(live) > 100, f"route walk collected only {len(live)} routes"
    return live, session_required


async def _set_role(user_id: uuid.UUID, role: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        user.role = role
        await session.commit()


def _fill(path: str) -> str:
    """Substitute a random UUID for every path parameter."""
    out = []
    for part in path.split("/"):
        out.append(str(uuid.uuid4()) if part.startswith("{") else part)
    return "/".join(out)


# ---------------------------------------------------------------------------
# 1a. Every exempt route is reachable without verification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(KYC_GATE_EXEMPT_ROUTES),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
@pytest.mark.asyncio
async def test_exempt_route_is_not_refused_by_the_gate(
    client: AsyncClient, method: str, path: str
) -> None:
    """One case per exempt route: the answer is anything but 402.

    Not "is 200": most of these want a body, a real id or a valid code,
    and answer 400/404/422 on this call. That is fine and beside the
    point -- what is measured is that the request reached the endpoint
    instead of being stopped by the gate.
    """
    data = await register_user(client, verified=False)
    headers = auth_headers(data["session_token"])

    resp = await client.request(method, _fill(path), headers=headers, json={})
    assert resp.status_code != 402, f"{method} {path} -> {resp.text}"


# ---------------------------------------------------------------------------
# 1b. The pair: routes outside the list are refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/dashboard/summary"),
        ("GET", "/api/v1/payments/history"),
        ("GET", "/api/v1/notifications/preferences"),
        ("GET", "/api/v1/users/me/payout-details"),
        ("GET", "/api/v1/transactions"),
    ],
)
@pytest.mark.asyncio
async def test_a_route_outside_the_list_is_refused(
    client: AsyncClient, method: str, path: str
) -> None:
    """Without this, every test above would pass on a gate that is off."""
    data = await register_user(client, verified=False)
    headers = auth_headers(data["session_token"])

    resp = await client.request(method, path, headers=headers)
    assert resp.status_code == 402, f"{method} {path} -> {resp.status_code}"
    assert resp.json()["error"].startswith("kyc_")


# ---------------------------------------------------------------------------
# 2. The refusal says which of the four situations this is
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_started_refusal_carries_the_two_amounts(
    client: AsyncClient,
) -> None:
    """kyc_payment_required is the only code that talks about money."""
    from app.modules.kyc.constants import KYC_VERIFICATION_FEE_CENTS
    from tests.helpers import fund_user

    data = await register_user(client, verified=False)
    user_id = uuid.UUID(data["user"]["id"])
    await fund_user(user_id, 300)

    resp = await client.get(
        "/api/v1/dashboard/summary",
        headers=auth_headers(data["session_token"]),
    )
    assert resp.status_code == 402
    body = resp.json()
    assert body["error"] == "kyc_payment_required"
    assert body["required_cents"] == KYC_VERIFICATION_FEE_CENTS
    assert body["available_cents"] == 300
    # The two fields every client in the tree reads are still there and
    # were not overwritten by the details payload.
    assert "message" in body


@pytest.mark.asyncio
async def test_pending_refusal_is_a_different_code(client: AsyncClient) -> None:
    """A paid, undecided session must not read as "pay again"."""
    from app.modules.kyc.constants import KYC_VERIFICATION_FEE_CENTS
    from tests.helpers import fund_user

    data = await register_user(client, verified=False)
    token = data["session_token"]
    await fund_user(uuid.UUID(data["user"]["id"]), KYC_VERIFICATION_FEE_CENTS)
    assert (
        await submit_kyc_application(client, token)
    ).status_code == 201

    resp = await client.get(
        "/api/v1/dashboard/summary", headers=auth_headers(token)
    )
    assert resp.status_code == 402
    assert resp.json()["error"] == "kyc_pending"
    # Not about money: no amounts on this branch.
    assert "required_cents" not in resp.json()


# ---------------------------------------------------------------------------
# 3. Roles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_passes_without_any_approval_record(
    client: AsyncClient, db_session
) -> None:
    """P-41: staff work by rule, not by a decision somebody recorded."""
    from app.modules.kyc.models import KYCApplication

    staff_user, staff_token = await create_admin_user(client, db_session)

    resp = await client.get(
        "/api/v1/staff/kyc/queue", headers=auth_headers(staff_token)
    )
    assert resp.status_code == 200

    applications = (
        await db_session.execute(
            select(KYCApplication).where(
                KYCApplication.user_id == staff_user.id
            )
        )
    ).scalars().all()
    assert applications == []


@pytest.mark.parametrize("role", [UserRole.AGENT, UserRole.COMPANY])
@pytest.mark.asyncio
async def test_agent_and_company_pass_by_role(
    client: AsyncClient, role: str
) -> None:
    """Neither deposits nor buys; both are created by staff."""
    data = await register_user(client, verified=False)
    await _set_role(uuid.UUID(data["user"]["id"]), role)

    resp = await client.get(
        "/api/v1/notifications", headers=auth_headers(data["session_token"])
    )
    assert resp.status_code != 402


def test_platform_and_unknown_roles_via_the_predicate() -> None:
    """PLATFORM cannot be tested over HTTP, and this says why in code.

    _load_user_from_request refuses a platform session with a 401 before
    any route runs, so a client-level test would have to hand-build a
    session the product never issues -- a test that constructs an
    unreachable state to assert on it. The rule itself is what matters
    here, and the predicate is where the rule lives.

    The unknown-role case is the fail-closed half: a role this file has
    never heard of is refused, not waved through.
    """
    assert is_gate_exempt_role(UserRole.PLATFORM) is True
    assert is_gate_exempt_role(UserRole.STAFF) is True
    assert is_gate_exempt_role(UserRole.AGENT) is True
    assert is_gate_exempt_role(UserRole.COMPANY) is True
    assert is_gate_exempt_role(UserRole.INVESTOR) is False
    assert is_gate_exempt_role("auditor") is False
    assert is_gate_exempt_role("") is False


# ---------------------------------------------------------------------------
# 4. The list against the live route table, both directions
# ---------------------------------------------------------------------------


def test_every_exempt_entry_names_a_live_session_route() -> None:
    """Direction one: the list must not rot.

    Renaming a path leaves a stale entry that opens nothing and reads,
    to the next person, as though it does. An entry for a route that
    needs no session is the same lie in the other direction -- it makes
    the list look like "everything reachable unverified", which it is
    not: login, registration, password reset and the payments webhook
    are open because they carry no user at all.
    """
    live, session_required = _route_sets()

    stale = sorted(KYC_GATE_EXEMPT_ROUTES - live)
    assert stale == [], f"exempt entries with no matching route: {stale}"

    sessionless = sorted(KYC_GATE_EXEMPT_ROUTES - session_required)
    assert sessionless == [], (
        f"exempt entries for routes that need no session: {sessionless}"
    )

    stale_gated = sorted(KYC_GATE_GATED_BY_DESIGN - live)
    assert stale_gated == [], f"gated-by-design with no route: {stale_gated}"


def test_no_route_in_a_reviewed_module_is_left_undecided() -> None:
    """Direction two: a new route in these modules demands a decision.

    Everywhere else the gate applies by default and silence is the right
    answer. In the modules a person needs in order to get in, pay, get
    out or ask for help, silence is how the self-lock gets rebuilt --
    so a new session-requiring route here fails this test until someone
    puts it in one list or the other.
    """
    _, session_required = _route_sets()

    undecided = sorted(
        key
        for key in session_required
        if key[1].startswith(KYC_GATE_REVIEWED_PREFIXES)
        and key not in KYC_GATE_EXEMPT_ROUTES
        and key not in KYC_GATE_GATED_BY_DESIGN
    )
    assert undecided == [], (
        "session-requiring routes in a reviewed module with no decision: "
        f"{undecided}"
    )


# ---------------------------------------------------------------------------
# 5. The gate does not touch requests that carry no valid user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anonymous_and_stale_token_requests_are_unchanged(
    client: AsyncClient,
) -> None:
    """The gate must not start answering for the unauthenticated.

    get_optional_user raises on a token that is present but invalid. If
    the gate let that escape, the public storefront would answer 401 to
    a browser holding a stale cookie -- today it serves the page.
    """
    anonymous = await client.get("/health")
    assert anonymous.status_code == 200

    stale = await client.get(
        "/health", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert stale.status_code == 200
