# =============================================================================
# AIVIS.ONE Backend -- KYC Gate (H10)
# =============================================================================
#
# An investor who has not passed verification is refused everywhere
# except a named list of routes. The refusal is a 402 carrying one of
# four codes (kyc/constants.py) so the client can tell "pay", "wait",
# "refused" and "revoked" apart.
#
# WIRED APP-WIDE, on the FastAPI() constructor, next to
# publish_background_tasks and for the same reason its comment gives:
# per-router opt-in leaves the trap armed for whoever adds the next
# router, and a forgotten gate is not visible in any output. App-wide
# means a route added tomorrow is gated by default and its author has to
# come here to open it -- the failure direction is a route that refuses
# when it should not, which a user reports on the first day, rather than
# a route that lets everyone through, which nobody reports at all.
#
# THE TWO LISTS BELOW ARE BOTH CHECKED BY tests/test_kyc_gate.py,
# in both directions: every exempt entry must match a real route that
# really requires a session, and every session-requiring route in the
# modules named here must appear in one list or the other. The second
# direction is why GATED_BY_DESIGN exists at all -- without it, adding a
# route to, say, payments would silently inherit the gate with nobody
# deciding whether it should.
#
# NOT A MIDDLEWARE: middleware runs before routing and would have to
# match "/api/v1/payments/invoices/{invoice_id}" against a raw path by
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
    KYC_VERIFICATION_FEE_CENTS,
)
from app.modules.ledgers.service import get_active_balance
from app.modules.users.models import KYCStatus, User, UserRole

# -----------------------------------------------------------------------------
# Roles
# -----------------------------------------------------------------------------
# A LIST OF WHO PASSES, NOT OF WHO IS STOPPED. A role this file has never
# heard of -- a value added to UserRole later, a row written by a script
# -- is not in this set and is therefore gated. Written the other way
# round, the same unknown role would sail through.
#
# The gate exists for the people who put money in and buy: investors.
# Staff and platform run the product. Agents earn commission and
# companies receive revenue; neither deposits, and both are created by
# staff, so demanding ten dollars and a manual approval from them would
# lock a company owner out of their own dashboard.
GATE_EXEMPT_ROLES: frozenset[str] = frozenset(
    {
        UserRole.STAFF,
        UserRole.PLATFORM,
        UserRole.AGENT,
        UserRole.COMPANY,
    }
)

# -----------------------------------------------------------------------------
# Routes open to an unverified investor
# -----------------------------------------------------------------------------
# (METHOD, path template) exactly as FastAPI records it on the route.
#
# ROUTES WITHOUT A SESSION ARE NOT LISTED HERE AND MUST NOT BE. Login,
# registration, password reset, the public storefront, the payments
# webhook and /health carry no user, and the gate's first branch lets
# every user-less request through. Listing them would make this file
# read as "everything that works without verification", which it is not.
#
# Three groups, and the third is the one the first draft of this list
# missed. Getting IN (onboarding: verify the address, choose a role,
# sign the documents), getting TO THE MONEY (the deposit screen's
# endpoints and the verification's own two), and -- for someone who has
# already paid and been refused -- getting OUT and getting ANSWERED:
# leaving the product, changing the address, and support. A gate that
# takes ten dollars at the entrance and locks the exit is not a gate.
KYC_GATE_EXEMPT_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        # -- Identity and session --------------------------------------
        ("POST", "/api/v1/auth/verify-email"),
        ("POST", "/api/v1/auth/verify-email/resend"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/logout-all"),
        ("GET", "/api/v1/auth/sessions"),
        ("DELETE", "/api/v1/auth/sessions/{session_id}"),
        ("POST", "/api/v1/auth/2fa/setup"),
        ("POST", "/api/v1/auth/2fa/confirm"),
        ("POST", "/api/v1/auth/2fa/disable"),
        # -- Profile, onboarding, and the way out ----------------------
        ("GET", "/api/v1/users/me"),
        ("PATCH", "/api/v1/users/me"),
        ("POST", "/api/v1/users/me/select-role"),
        ("POST", "/api/v1/users/me/deactivate"),
        ("POST", "/api/v1/users/me/email-change"),
        ("POST", "/api/v1/users/me/email-change/resend"),
        ("POST", "/api/v1/users/me/email-change/confirm"),
        # -- Onboarding documents --------------------------------------
        ("GET", "/api/v1/documents"),
        ("GET", "/api/v1/documents/{document_id}"),
        ("POST", "/api/v1/documents/{document_id}/sign"),
        # -- Topping up ------------------------------------------------
        # The deposit screen and nothing else. GET /payments/history is
        # deliberately absent: it is a record of past movement, not a
        # way to fund the account.
        ("POST", "/api/v1/payments/invoices"),
        ("GET", "/api/v1/payments/invoices/current"),
        ("GET", "/api/v1/payments/invoices/{invoice_id}"),
        ("POST", "/api/v1/payments/invoices/{invoice_id}/txid"),
        # -- Verification itself ---------------------------------------
        # Without these the gate stands in front of the only door
        # through it.
        ("GET", "/api/v1/kyc/status"),
        ("POST", "/api/v1/kyc/submit"),
        # -- Inbox, read side ------------------------------------------
        # The decision arrives as a notification. Preferences stay
        # behind the gate: that is a setting, not a message.
        ("GET", "/api/v1/notifications"),
        ("GET", "/api/v1/notifications/unread-count"),
        ("POST", "/api/v1/notifications/{delivery_id}/read"),
        ("POST", "/api/v1/notifications/read-all"),
        # -- Support, whole module -------------------------------------
        # Someone who paid and was refused has no other human recourse,
        # and there is no money in support. Listed route by route rather
        # than by prefix on purpose: a prefix rule would also switch off
        # the route walk for this module, and the walk is the thing that
        # makes the list trustworthy.
        ("POST", "/api/v1/support/threads"),
        ("GET", "/api/v1/support/threads"),
        ("POST", "/api/v1/support/threads/messages"),
        ("GET", "/api/v1/support/threads/{thread_id}/messages"),
        ("POST", "/api/v1/support/threads/{thread_id}/read"),
    }
)

# Session-requiring routes in the same modules that stay behind the gate.
# Not consulted at runtime -- the gate refuses anything not exempt, with
# or without this set. It exists so that the route walk can demand a
# DECISION for every new route in these modules instead of letting it
# inherit the gate unread.
KYC_GATE_GATED_BY_DESIGN: frozenset[tuple[str, str]] = frozenset(
    {
        # History is not a path to the money.
        ("GET", "/api/v1/payments/history"),
        # Delivery settings, not the inbox.
        ("GET", "/api/v1/notifications/preferences"),
        ("PATCH", "/api/v1/notifications/preferences"),
        # Where a withdrawal is paid out to. Behind the gate by
        # intention: an unverified account has nothing to withdraw.
        ("GET", "/api/v1/users/me/payout-details"),
        ("PUT", "/api/v1/users/me/payout-details"),
    }
)

# Prefixes whose routes the walk demands a decision for. Modules outside
# this list are gated by default and need no entry anywhere.
KYC_GATE_REVIEWED_PREFIXES: tuple[str, ...] = (
    "/api/v1/auth/",
    "/api/v1/users/",
    "/api/v1/documents",
    "/api/v1/payments/",
    "/api/v1/kyc/",
    "/api/v1/notifications",
    "/api/v1/support/",
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
        "Identity verification is required before using the platform."
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
    """App-wide gate: refuse unverified investors outside the exempt list.

    Loads the user itself rather than reusing the route's own dependency:
    routes resolve their user through get_current_user,
    get_current_user_write or a staff dependency, and FastAPI caches by
    callable, so there is no single object to share. The cost is one
    extra SELECT on requests whose route loads a user for writing --
    accepted, and named in the H10 report rather than hidden here.
    """
    try:
        user: User | None = await get_optional_user(request, session)
    except UnauthorizedError:
        # A token that is present but invalid. Not the gate's business:
        # letting it through leaves the answer exactly as it was before
        # this file existed -- 401 from a protected route's own
        # dependency, and the public storefront still served. Raising
        # here instead would start answering 401 for anonymous-friendly
        # routes that merely saw a stale cookie.
        return

    if user is None:
        return

    if is_gate_exempt_role(user.role):
        return

    if user.kyc_status == KYCStatus.APPROVED:
        return

    route_key = (request.method, request.scope["route"].path)
    if route_key in KYC_GATE_EXEMPT_ROUTES:
        return

    code = _REFUSAL_CODES[user.kyc_status]

    details: dict | None = None
    if code == KYC_CODE_PAYMENT_REQUIRED:
        # Only on this branch: the other three are not about money, and
        # a balance read on every refusal would be a query bought for
        # nothing. The client needs both numbers to say "top up $7
        # more", and the deposit screen's own source of balance
        # (dashboard/summary) is itself behind the gate.
        balance = await get_active_balance(session, user.id)
        # No cast here any more (H12 P-46g). It used to be load-bearing:
        # get_active_balance was annotated dict[str, int] and handed
        # back Decimal, and JSONResponse raises TypeError on a Decimal,
        # so without it the gate answered 500 instead of 402 to any
        # unverified user who had ever had a ledger row. The function
        # now returns what it promises, and the guarantee sits there
        # rather than in each caller that remembered.
        details = {
            "required_cents": KYC_VERIFICATION_FEE_CENTS,
            "available_cents": balance["frozen"] + balance["confirmed"],
        }

    raise KYCGateError(
        message=_MESSAGES[code],
        code=code,
        details=details,
    )
