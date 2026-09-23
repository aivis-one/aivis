# =============================================================================
# AIVIS.ONE Backend -- KYC Gate Tests (H10, turned over H21 P-111)
# =============================================================================
#
# The gate closes a named list of money routes to an unverified investor
# and lets everything else through. These tests measure four separate
# things, and the last is the one that keeps the others honest:
#
#   1. Every closed route is refused, and every route decided open is
#      not. EACH HALF WITHOUT THE OTHER passes against a broken gate: the
#      first against one that refuses everything, the second against one
#      that was never wired up at all.
#   2. The refusal carries a code the client can act on, one per state,
#      and nothing else -- every state the gate can meet on a closed
#      route, sections 2 and 6.
#   3. Roles.
#   4. The two lists match the live route table: every route that can
#      write and that an unverified investor can reach has a decision,
#      and no entry names anything else. Sections 4 and 8; section 8
#      also proves the walk's one exclusion (routes under staff, support
#      or company authorisation) over HTTP.
#   5. Public routes are served to a signed-in unverified investor,
#      section 7 -- the finding that turned the walk app-wide.
#
# MUTATIONS THIS FILE IS BUILT TO CATCH:
#   * remove Depends(enforce_kyc_gate) from main.py
#       -> every case of test_closed_route_is_refused fails
#   * make the gate refuse by default again
#       -> test_open_by_decision_route_is_not_refused and
#          test_reads_that_the_old_gate_closed_are_open fail
#   * add a new writing route and decide nothing
#       -> test_every_reachable_writing_route_has_a_decision fails
#   * rename a route without updating a list
#       -> the same walk fails from the other side
# =============================================================================

import uuid

import pytest
from httpx import AsyncClient

from app.core.database import get_db_session, get_session_factory
from app.main import app
from app.modules.auth.dependencies import (
    get_current_staff,
    require_staff_permission,
)
from app.modules.companies.dependencies import get_current_company_profile
from app.modules.kyc.gate import (
    _REFUSAL_CODES,
    KYC_GATE_CLOSED_ROUTES,
    KYC_GATE_OPEN_BY_DECISION,
    is_gate_exempt_role,
)
from app.modules.payments.webhook import verify_payments_secret
from app.modules.support.dependencies import get_support_operator
from app.modules.users.models import KYCStatus, User, UserRole
from sqlalchemy import select
from tests.helpers import (
    auth_headers,
    create_admin_user,
    register_user,
    set_kyc_status,
    submit_kyc_application,
)

# ---------------------------------------------------------------------------
# Live route table -- the source, not a re-parse of the source code
# ---------------------------------------------------------------------------

# AUTHORISATION THAT REFUSES AN INVESTOR ON ITS OWN. A route whose
# dependency tree holds one of these is unreachable to an unverified
# investor whatever the gate does, so the walk does not demand a gate
# decision for it. Named here rather than inferred, because two of them
# hide their check from the tree: get_support_operator calls
# get_current_staff as a plain function, not through Depends, and
# require_staff_permission builds a fresh closure per permission.
# test_foreign_authorisation_refuses_an_investor proves the claim for
# every member that actually excludes a route.
_FOREIGN_AUTH = {
    get_current_staff,
    get_support_operator,
    get_current_company_profile,
    verify_payments_secret,
}
_FOREIGN_AUTH_FACTORY_PREFIX = require_staff_permission.__qualname__ + ".<locals>."


def _foreign_auth_name(call) -> str | None:
    if call in _FOREIGN_AUTH:
        return call.__qualname__
    qualname = getattr(call, "__qualname__", "")
    if qualname.startswith(_FOREIGN_AUTH_FACTORY_PREFIX):
        return qualname
    return None


def _calls(dependant, acc: set) -> set:
    """Every callable in a route's dependency tree, at any depth."""
    for sub in dependant.dependencies:
        acc.add(sub.call)
        _calls(sub, acc)
    return acc


def _collect(routes, table: dict) -> None:
    """Walk app.routes, descending into lazily-included routers.

    FastAPI stopped flattening include_router: app.routes holds
    _IncludedRouter placeholders, and a flat loop over it sees three
    routes instead of a hundred and eighty-six -- every assertion below
    would pass while measuring nothing. Same descent as test_avatar.py.

    table maps (method, path) -> (writes, foreign_auth_name | None).
    """
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            _collect(inner.routes, table)
            continue
        dependant = getattr(route, "dependant", None)
        if dependant is None or not getattr(route, "methods", None):
            continue
        calls = _calls(dependant, set())
        foreign = sorted(
            name for name in map(_foreign_auth_name, calls) if name is not None
        )
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            # A GET that holds a write session can commit, so it is a
            # writer. "Only reads" is proven by the absence of that
            # session, not assumed from the method.
            writes = method != "GET" or get_db_session in calls
            table[(method, route.path)] = (writes, foreign[0] if foreign else None)


def _route_table() -> dict:
    table: dict = {}
    _collect(app.routes, table)
    # A flat walk returns almost nothing; if the descent above ever
    # breaks, fail here rather than passing everything downstream.
    assert len(table) > 100, f"route walk collected only {len(table)} routes"
    return table


def _reachable_writers(table: dict) -> set:
    """Routes that can write and that an unverified investor can reach."""
    return {
        key
        for key, (writes, foreign) in table.items()
        if writes and foreign is None
    }


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


_A_CLOSED_ROUTE = ("POST", "/api/v1/withdrawals")


# ---------------------------------------------------------------------------
# 1a. Every closed route is refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(KYC_GATE_CLOSED_ROUTES),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
@pytest.mark.asyncio
async def test_closed_route_is_refused(
    client: AsyncClient, method: str, path: str
) -> None:
    """One case per closed route: 402 with a kyc_ code.

    Until H21 this was a fixed set of five reads (dashboard summary,
    payment history, notification preferences, payout details,
    transactions) that sat outside the exempt list. It was right that a
    route outside the list was refused; the owner's decision that the
    product is open before verification made all five open, and the
    claim now holds for the closed list instead. The five are asserted
    open below, in test_reads_that_the_old_gate_closed_are_open.
    """
    data = await register_user(client, verified=False)
    headers = auth_headers(data["session_token"])

    resp = await client.request(method, _fill(path), headers=headers, json={})
    assert resp.status_code == 402, f"{method} {path} -> {resp.status_code}"
    assert resp.json()["error"].startswith("kyc_")


# ---------------------------------------------------------------------------
# 1b. The pair: routes decided open are not refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(KYC_GATE_OPEN_BY_DECISION),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
@pytest.mark.asyncio
async def test_open_by_decision_route_is_not_refused(
    client: AsyncClient, method: str, path: str
) -> None:
    """One case per open-by-decision route: the answer is anything but 402.

    Not "is 200": most of these want a body, a real id or a valid code,
    and answer 400/404/422 on this call. That is fine and beside the
    point -- what is measured is that the request reached the endpoint
    instead of being stopped by the gate. Until H21 this ran over the
    exempt list, which was the list of what the gate let through; the
    open list is now the decided half of what it does not close.
    """
    data = await register_user(client, verified=False)
    headers = auth_headers(data["session_token"])

    resp = await client.request(method, _fill(path), headers=headers, json={})
    assert resp.status_code != 402, f"{method} {path} -> {resp.text}"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dashboard/summary",
        "/api/v1/payments/history",
        "/api/v1/notifications/preferences",
        "/api/v1/users/me/payout-details",
        "/api/v1/transactions",
    ],
)
@pytest.mark.asyncio
async def test_reads_that_the_old_gate_closed_are_open(
    client: AsyncClient, path: str
) -> None:
    """The five reads the H10 gate refused now answer 200.

    Asserted as 200 and not merely "not 402": these need no body and no
    id, so anything short of success is a failure worth seeing. The
    dashboard summary is the one that mattered -- it is the first
    screen after onboarding, and its 402 was the wall P-111 removes.
    """
    data = await register_user(client, verified=False)
    headers = auth_headers(data["session_token"])

    resp = await client.get(path, headers=headers)
    assert resp.status_code == 200, f"{path} -> {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# 2. The refusal says which of the four situations this is
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_started_refusal_carries_the_code_and_nothing_else(
    client: AsyncClient,
) -> None:
    """kyc_payment_required: code and message, no amounts.

    Until H21 this refusal carried required_cents and available_cents,
    because the deposit screen's own source of balance
    (dashboard/summary) was itself behind the gate. That reason is gone
    -- the summary is open -- and no client read the two fields: the
    verification screen takes both numbers from GET /kyc/status. They
    were removed with the reason, and the assertion is now that the body
    is exactly the two fields every client reads.
    """
    from tests.helpers import fund_user

    data = await register_user(client, verified=False)
    await fund_user(uuid.UUID(data["user"]["id"]), 300)

    method, path = _A_CLOSED_ROUTE
    resp = await client.request(
        method, path, headers=auth_headers(data["session_token"]), json={}
    )
    assert resp.status_code == 402
    body = resp.json()
    assert set(body) == {"error", "message"}
    assert body["error"] == "kyc_payment_required"
    assert body["message"]


@pytest.mark.asyncio
async def test_pending_refusal_is_a_different_code(client: AsyncClient) -> None:
    """A paid, undecided session must not read as "pay again".

    Until H21 measured on GET /dashboard/summary, which is open now; the
    claim is about the code, so it moved to a closed route unchanged.
    """
    from app.modules.kyc.constants import KYC_VERIFICATION_FEE_CENTS
    from tests.helpers import fund_user

    data = await register_user(client, verified=False)
    token = data["session_token"]
    await fund_user(uuid.UUID(data["user"]["id"]), KYC_VERIFICATION_FEE_CENTS)
    assert (
        await submit_kyc_application(client, token)
    ).status_code == 201

    method, path = _A_CLOSED_ROUTE
    resp = await client.request(method, path, headers=auth_headers(token), json={})
    assert resp.status_code == 402
    assert resp.json()["error"] == "kyc_pending"
    assert set(resp.json()) == {"error", "message"}


# ---------------------------------------------------------------------------
# 3. Roles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_passes_without_any_approval_record(
    client: AsyncClient, db_session
) -> None:
    """P-41: staff work by rule, not by a decision somebody recorded.

    H17 P-85: this used to hit /staff/kyc/queue, which is deleted this
    pass (no frontend consumer since iter 2.7 A2). The route named
    here was never the point -- any staff-only, kyc_status-independent
    route works, since the claim under test is that the ROLE clears
    the gate, not that this particular permission does. Swapped for
    /staff/users, which if anything states that more precisely: it
    requires no permission beyond being staff at all (see
    staff/router.py's user_list -- Depends(get_current_staff), no
    require_staff_permission), so passing it is about the role alone
    and not about which permissions this staff profile happens to
    carry.
    """
    from app.modules.kyc.models import KYCApplication

    staff_user, staff_token = await create_admin_user(client, db_session)

    resp = await client.get(
        "/api/v1/staff/users", headers=auth_headers(staff_token)
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
    """Neither deposits nor buys; both are created by staff.

    Until H21 measured on GET /notifications, which was gated for an
    investor then and proved something. It is open to everyone now, so
    the same call would pass for any role and prove nothing; the claim
    moved to a closed route, where only the role can explain a pass.
    """
    data = await register_user(client, verified=False)
    await _set_role(uuid.UUID(data["user"]["id"]), role)

    method, path = _A_CLOSED_ROUTE
    resp = await client.request(
        method, path, headers=auth_headers(data["session_token"]), json={}
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
    never heard of is refused on the closed routes, not waved through.
    """
    assert is_gate_exempt_role(UserRole.PLATFORM) is True
    assert is_gate_exempt_role(UserRole.STAFF) is True
    assert is_gate_exempt_role(UserRole.AGENT) is True
    assert is_gate_exempt_role(UserRole.COMPANY) is True
    assert is_gate_exempt_role(UserRole.INVESTOR) is False
    assert is_gate_exempt_role("auditor") is False
    assert is_gate_exempt_role("") is False


# ---------------------------------------------------------------------------
# 4. The lists against the live route table
# ---------------------------------------------------------------------------


def test_every_reachable_writing_route_has_a_decision() -> None:
    """A route that can write and that an investor can reach is decided.

    Replaces the two H10 walks (every exempt entry names a live session
    route; no session route in a reviewed module is undecided). Both were
    right for a gate that closed by default, and both measured the wrong
    universe: they looked only at routes requiring a session, inside
    seven prefixes, while the gate reads the Bearer header on EVERY
    request -- a signed-in browser met it on the public storefront and
    on /health. The walk now covers the whole app, and what it requires
    a decision for is what can move money: a route that writes.

    Both directions in one assertion pair: nothing reachable left
    undecided, and no entry naming a route that does not exist, only
    reads, or is closed to an investor by its own authorisation.
    """
    table = _route_table()
    universe = _reachable_writers(table)
    decided = KYC_GATE_CLOSED_ROUTES | KYC_GATE_OPEN_BY_DECISION

    undecided = sorted(universe - decided)
    assert undecided == [], (
        "writing routes an unverified investor can reach, with no "
        f"decision in kyc/gate.py: {undecided}"
    )

    outside = sorted(decided - universe)
    assert outside == [], (
        "entries naming no reachable writing route (renamed, read-only, "
        f"or under staff/company authorisation): {outside}"
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


# ---------------------------------------------------------------------------
# 6. Every state the gate can meet on a closed route (H21)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (KYCStatus.NOT_STARTED, "kyc_payment_required"),
        (KYCStatus.SUBMITTED, "kyc_pending"),
        (KYCStatus.REJECTED, "kyc_rejected"),
        (KYCStatus.REVOKED, "kyc_revoked"),
    ],
)
@pytest.mark.asyncio
async def test_each_unverified_status_is_refused_with_its_own_code(
    client: AsyncClient, status: str, code: str
) -> None:
    """All four refusing states over HTTP, each with its own code.

    The status is written straight to the row: the claim is about what
    the gate does with a status, not about how a person comes to hold
    it, which test_kyc.py covers.
    """
    data = await register_user(client, verified=False)
    await set_kyc_status(data["user"]["id"], status)

    method, path = _A_CLOSED_ROUTE
    resp = await client.request(
        method, path, headers=auth_headers(data["session_token"]), json={}
    )
    assert resp.status_code == 402
    assert resp.json() == {"error": code, "message": resp.json()["message"]}
    assert resp.json()["message"]


@pytest.mark.asyncio
async def test_an_approved_investor_passes_a_closed_route(
    client: AsyncClient,
) -> None:
    """The pair of the case above: approval is what opens the route."""
    data = await register_user(client, verified=True)

    method, path = _A_CLOSED_ROUTE
    resp = await client.request(
        method, path, headers=auth_headers(data["session_token"]), json={}
    )
    assert resp.status_code != 402


def test_refusal_codes_cover_every_status_except_approved() -> None:
    """No status can reach the lookup without a code -- the missing-key axis.

    The gate has no default arm on purpose (see _REFUSAL_CODES); this is
    what makes that safe when a status is added to KYCStatus.
    """
    assert set(_REFUSAL_CODES) == set(KYCStatus) - {KYCStatus.APPROVED}
    assert all(_REFUSAL_CODES.values())


@pytest.mark.asyncio
async def test_a_stale_token_on_a_closed_route_is_the_routes_401(
    client: AsyncClient,
) -> None:
    """An invalid token passes the gate and meets the route's own 401."""
    method, path = _A_CLOSED_ROUTE
    resp = await client.request(
        method,
        path,
        headers={"Authorization": "Bearer not-a-real-token"},
        json={},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_a_deactivated_account_on_a_closed_route_is_403(
    client: AsyncClient,
) -> None:
    """ForbiddenError from the user lookup must surface, not be swallowed.

    The session is left alive and only the row is switched off -- the
    state an admin deactivation leaves between its write and the
    session sweep. The gate must answer 403 through the error handler
    (H18 P-60a), not let the request through and not answer 402.
    """
    data = await register_user(client, verified=False)
    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(User, uuid.UUID(data["user"]["id"]))
        user.is_active = False
        await session.commit()

    method, path = _A_CLOSED_ROUTE
    resp = await client.request(
        method, path, headers=auth_headers(data["session_token"]), json={}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 7. The finding behind H21: the gate saw every Bearer, not every session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/api/v1/public/products",
        "/api/v1/public/companies",
        "/api/v1/posts",
        "/api/v1/events",
    ],
)
@pytest.mark.asyncio
async def test_public_routes_serve_a_signed_in_unverified_investor(
    client: AsyncClient, path: str
) -> None:
    """The frontend sends Bearer on every request once signed in.

    Until H21 the gate loaded the user from that header on every route,
    so a signed-in unverified investor got 402 on the storefront and on
    /health while an anonymous visitor was served. Asserted as 200: none
    of these needs a body or an id.
    """
    data = await register_user(client, verified=False)

    resp = await client.get(path, headers=auth_headers(data["session_token"]))
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"


# ---------------------------------------------------------------------------
# 8. The lists themselves: repeat, emptiness, and the foreign set
# ---------------------------------------------------------------------------


def test_the_closed_list_is_exactly_the_money_and_no_entry_is_in_both() -> None:
    """Emptiness and repeat on the two lists.

    Pinned to the literal set rather than "non-empty": the closed list is
    the owner's criterion made concrete, and changing it is a decision
    that should have to touch this line too.
    """
    expected = {
        ("POST", "/api/v1/products/{product_id}/purchase"),
        ("POST", "/api/v1/products/{product_id}/installment"),
        ("POST", "/api/v1/withdrawals"),
        ("POST", "/api/v1/agent-applications"),
    }
    assert expected == KYC_GATE_CLOSED_ROUTES
    assert KYC_GATE_OPEN_BY_DECISION
    overlap = KYC_GATE_CLOSED_ROUTES & KYC_GATE_OPEN_BY_DECISION
    assert not overlap, f"in both lists: {sorted(overlap)}"


def test_every_foreign_authorisation_is_live() -> None:
    """A member of _FOREIGN_AUTH that guards no route is a stale exclusion.

    Without this, renaming get_current_staff would leave the set naming
    nothing -- and every staff route would drop into the walk's universe
    with a failure message that points away from the real cause.
    """
    table = _route_table()
    live = {foreign for _, foreign in table.values() if foreign is not None}

    for call in _FOREIGN_AUTH:
        assert call.__qualname__ in live, f"{call.__qualname__} guards no route"
    assert any(
        name.startswith(_FOREIGN_AUTH_FACTORY_PREFIX) for name in live
    ), "require_staff_permission guards no route"


def _foreign_samples() -> list[tuple[str, str, str]]:
    """One writing route per foreign authorisation that excludes any."""
    samples: dict[str, tuple[str, str]] = {}
    for (method, path), (writes, foreign) in sorted(_route_table().items()):
        if writes and foreign is not None and foreign not in samples:
            samples[foreign] = (method, path)
    return [(name, m, p) for name, (m, p) in sorted(samples.items())]


@pytest.mark.parametrize(
    ("foreign", "method", "path"),
    _foreign_samples(),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
@pytest.mark.asyncio
async def test_foreign_authorisation_refuses_an_investor(
    client: AsyncClient, foreign: str, method: str, path: str
) -> None:
    """The walk's exclusion, proven: the route itself refuses an investor.

    The completeness walk leaves out every route guarded by a member of
    _FOREIGN_AUTH on the claim that an investor cannot reach it anyway.
    This is that claim over HTTP, one route per member that actually
    excludes something: 401 or 403 -- never 402, which would mean the
    gate answered, and never a success.
    """
    data = await register_user(client, verified=False)

    resp = await client.request(
        method,
        _fill(path),
        headers=auth_headers(data["session_token"]),
        json={},
    )
    assert resp.status_code in (401, 403), (
        f"{foreign}: {method} {path} -> {resp.status_code}"
    )
