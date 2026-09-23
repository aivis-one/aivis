# =============================================================================
# AIVIS.ONE Backend -- KYC Gate (H10, turned over H21 P-111)
# =============================================================================
#
# OWNER'S DECISION, NOT A DEFERRED TASK: before verification a person sees
# the product -- dashboard, storefront, products, companies, history,
# settings. What is closed is exactly what turns a balance into
# ownership or takes money out. The gate therefore holds a list of what
# it CLOSES, and everything else passes it. The refusal is a 402 carrying
# one of four codes (kyc/constants.py) so the client can tell "pay",
# "wait", "refused" and "revoked" apart.
#
# Until H21 it was the other way round -- closed everywhere except a list
# of exemptions -- and the first screen after onboarding
# (GET /dashboard/summary) was a wall. The inversion changes the failure
# direction as well: a new route is open by default. That is why the
# completeness walk in tests/test_kyc_gate.py demands a decision for
# every route that can WRITE and that an unverified investor can reach,
# across the whole app: such a route is either in KYC_GATE_CLOSED_ROUTES
# or in KYC_GATE_OPEN_BY_DECISION, and a route in neither fails the walk
# until somebody decides. Routes that only read are not in the walk:
# reading moves no money, and the walk proves "only reads" by the absence
# of a write session in the route's dependency tree, not by the method.
#
# WIRED APP-WIDE, on the FastAPI() constructor, next to
# publish_background_tasks: per-router opt-in would leave the next
# router's money route ungated with nothing visible in any output.
#
# THE ROUTE IS CHECKED BEFORE THE USER IS LOADED. A request to a route
# that is not closed never reaches the user lookup, so the gate costs
# nothing there and cannot answer for a route it has no business with.
# The consequence is deliberate: a public route called with a Bearer
# header -- the frontend sends one on every request once signed in -- is
# served whatever the account's verification state.
#
# NOT A MIDDLEWARE: middleware runs before routing and would have to
# match "/api/v1/products/{product_id}/purchase" against a raw path by
# hand, i.e. reimplement the router. As a dependency the gate reads the
# matched route's template straight out of the scope.
# =============================================================================

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_reader
from app.core.exceptions import KYCGateError, UnauthorizedError
from app.modules.auth.dependencies import get_optional_user
from app.modules.kyc.constants import (
    KYC_CODE_PAYMENT_REQUIRED,
    KYC_CODE_PENDING,
    KYC_CODE_REJECTED,
    KYC_CODE_REVOKED,
)
from app.modules.users.models import KYCStatus, User, UserRole

# -----------------------------------------------------------------------------
# Roles
# -----------------------------------------------------------------------------
# A LIST OF WHO PASSES, NOT OF WHO IS STOPPED. A role this file has never
# heard of -- a value added to UserRole later, a row written by a script
# -- is not in this set and is therefore refused on the closed routes.
# Written the other way round, the same unknown role would sail through.
#
# The gate exists for the people who put money in and buy: investors.
# Staff and platform run the product. Agents earn commission and
# companies receive revenue; neither deposits, and both are created by
# staff, so demanding ten dollars and a manual approval from them would
# stop a company owner from withdrawing its own revenue. The service-level
# KYC refusals in purchases/service.py and installments/service.py stay
# for exactly these roles: for an agent they are the only lock.
GATE_EXEMPT_ROLES: frozenset[str] = frozenset(
    {
        UserRole.STAFF,
        UserRole.PLATFORM,
        UserRole.AGENT,
        UserRole.COMPANY,
    }
)

# -----------------------------------------------------------------------------
# Routes closed to an unverified investor
# -----------------------------------------------------------------------------
# (METHOD, path template) exactly as FastAPI records it on the route. The
# only list the gate consults at runtime.
KYC_GATE_CLOSED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        # Balance -> ownership.
        ("POST", "/api/v1/products/{product_id}/purchase"),
        # Balance -> ownership, paid in tranches.
        ("POST", "/api/v1/products/{product_id}/installment"),
        # Money out.
        ("POST", "/api/v1/withdrawals"),
        # The door to a role the gate does not stop. An approved
        # application makes the investor an agent, agents are in
        # GATE_EXEMPT_ROLES, and withdrawals/service.py has no KYC check
        # of its own -- so an open application route would let an
        # unverified depositor reach POST /withdrawals through staff
        # approval. This route is the only thing on the backend that
        # holds "applying requires verification", which the investor
        # settings screen already states.
        ("POST", "/api/v1/agent-applications"),
    }
)

# -----------------------------------------------------------------------------
# Routes that write and stay open to an unverified investor, by decision
# -----------------------------------------------------------------------------
# NOT CONSULTED AT RUNTIME: a route missing from the closed list passes
# with or without an entry here. The set exists so the completeness walk
# can tell "decided open" from "nobody looked". Sessionless routes are in
# it on purpose: the gate sees the Bearer header on every request, so a
# route that needs no session is still within its reach.
KYC_GATE_OPEN_BY_DECISION: frozenset[tuple[str, str]] = frozenset(
    {
        # -- Getting in, sessionless ------------------------------------
        ("POST", "/api/v1/auth/email/register"),
        ("POST", "/api/v1/auth/email/login"),
        ("POST", "/api/v1/auth/telegram"),
        ("POST", "/api/v1/auth/2fa/login-verify"),
        ("POST", "/api/v1/auth/password-reset/request"),
        ("POST", "/api/v1/auth/password-reset/confirm"),
        ("POST", "/api/v1/public/referral-click"),
        # -- Identity and session --------------------------------------
        ("POST", "/api/v1/auth/verify-email"),
        ("POST", "/api/v1/auth/verify-email/resend"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/logout-all"),
        ("DELETE", "/api/v1/auth/sessions/{session_id}"),
        ("POST", "/api/v1/auth/2fa/setup"),
        ("POST", "/api/v1/auth/2fa/confirm"),
        ("POST", "/api/v1/auth/2fa/disable"),
        # -- Profile, onboarding, settings -----------------------------
        ("PATCH", "/api/v1/users/me"),
        ("POST", "/api/v1/users/me/select-role"),
        ("POST", "/api/v1/users/me/deactivate"),
        ("POST", "/api/v1/documents/{document_id}/sign"),
        ("PATCH", "/api/v1/notifications/preferences"),
        # Where a withdrawal would be paid out to. A setting, not a
        # movement: the money leaves only through POST /withdrawals,
        # which is closed.
        ("PUT", "/api/v1/users/me/payout-details"),
        # -- Topping up ------------------------------------------------
        # Money in, not out. The two GETs are here because they hold a
        # write session, which puts them in the walk.
        ("POST", "/api/v1/payments/invoices"),
        ("GET", "/api/v1/payments/invoices/current"),
        ("GET", "/api/v1/payments/invoices/{invoice_id}"),
        ("POST", "/api/v1/payments/invoices/{invoice_id}/txid"),
        # -- Verification itself ---------------------------------------
        # Takes the fee from the balance, but it is the way through the
        # gate, not past it.
        ("POST", "/api/v1/kyc/submit"),
        # -- Inbox, content, referrals ---------------------------------
        ("POST", "/api/v1/notifications/{delivery_id}/read"),
        ("POST", "/api/v1/notifications/read-all"),
        ("POST", "/api/v1/posts/{post_id}/dismiss"),
        ("POST", "/api/v1/referrals/links"),
        # -- Documents of things already owned -------------------------
        # A copy of an agreement or certificate by email. An unverified
        # investor owns nothing, so these answer 404 for them.
        ("POST", "/api/v1/purchases/{purchase_id}/agreement/email"),
        ("POST", "/api/v1/companies/{company_id}/ownership-certificate/email"),
        # -- Support ---------------------------------------------------
        ("POST", "/api/v1/support/threads"),
        ("POST", "/api/v1/support/threads/messages"),
        ("POST", "/api/v1/support/threads/{thread_id}/read"),
    }
)

# status -> refusal code. Covers every KYCStatus except APPROVED, which
# never reaches the lookup. No default arm: kyc_status is guarded by
# ck_users_kyc_status, so a value missing from this dict cannot exist in
# the database, and inventing a branch for it would put a lie in the
# file for the next reader.
_REFUSAL_CODES: dict[str, str] = {
    KYCStatus.NOT_STARTED: KYC_CODE_PAYMENT_REQUIRED,
    KYCStatus.SUBMITTED: KYC_CODE_PENDING,
    KYCStatus.REJECTED: KYC_CODE_REJECTED,
    KYCStatus.REVOKED: KYC_CODE_REVOKED,
}

_MESSAGES: dict[str, str] = {
    KYC_CODE_PAYMENT_REQUIRED: (
        "Identity verification is required to buy, pay in installments "
        "or withdraw."
    ),
    KYC_CODE_PENDING: (
        "Identity verification has been paid for and is awaiting a "
        "decision."
    ),
    KYC_CODE_REJECTED: "Identity verification was not approved.",
    KYC_CODE_REVOKED: "Identity verification approval was withdrawn.",
}


def is_gate_exempt_role(role: str) -> bool:
    """Whether this role passes the gate by rule rather than by decision.

    Separate from the dependency so the rule can be tested directly.
    UserRole.PLATFORM cannot reach the dependency over HTTP at all --
    _load_user_from_request refuses platform sessions with a 401 before
    any route runs -- so a client-level test of that role would have to
    hand-build a session that the product never issues.
    """
    return role in GATE_EXEMPT_ROLES


async def enforce_kyc_gate(
    request: Request,
    session: AsyncSession = Depends(get_db_reader),
) -> None:
    """App-wide gate: refuse unverified investors on the closed routes.

    The route is checked first and the user is loaded only for a closed
    route -- see the file header for what that does to public routes
    called with a Bearer header.

    Loads the user itself rather than reusing the route's own dependency:
    FastAPI caches by callable and the closed routes resolve their user
    through get_current_user_write, so there is no single object to
    share. The cost is one extra SELECT on the closed routes only.
    """
    route_key = (request.method, request.scope["route"].path)
    if route_key not in KYC_GATE_CLOSED_ROUTES:
        return

    try:
        user: User | None = await get_optional_user(request, session)
    except UnauthorizedError:
        # A token that is present but invalid. Not the gate's business:
        # the route's own session dependency answers 401 right after.
        return
    # Do NOT add `except ForbiddenError: return` to match the branch
    # above -- a deactivated account must reach aivis_error_handler as
    # 403 (H18 P-60a report); catching it here the way UnauthorizedError
    # is caught would let it through silently.

    if user is None:
        return

    if is_gate_exempt_role(user.role):
        return

    if user.kyc_status == KYCStatus.APPROVED:
        return

    code = _REFUSAL_CODES[user.kyc_status]
    raise KYCGateError(message=_MESSAGES[code], code=code)
