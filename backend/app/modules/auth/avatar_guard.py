# =============================================================================
# AIVIS.ONE Backend -- Avatar Guard (Sprint 1.3, dependency-layer R49)
# =============================================================================
#
# Blocks certain operations when Staff is in avatar mode (logged in as
# another user via Sprint 3.2 avataring) -- BUT ONLY WHILE THE SWITCH IS ON,
# and as of 2026-08-17 it is OFF by default.
#
# THE SWITCH (settings.avatar_restrictions_enabled, owner-ruled 2026-08-17):
#   False (default) -- every operation below is ALLOWED in avatar mode. The
#     product is being tested single-handedly through the admin account, and
#     a guard that blocks the tester tests nothing.
#   True -- the behaviour described in the rest of this header applies.
#   The route wiring is deliberately NOT removed. Turning the switch on
#   restores all six guards at once, and the planned per-operation toggle
#   extends this dependency rather than rebuilding the plumbing. The division
#   there is by CAPABILITY, not by role -- his words.
#
# HOW IT WORKS:
#   _load_user_from_request() (auth/dependencies.py) binds
#   avatar_session_id to structlog contextvars when the Redis session
#   contains it. The forbid_avatar() dependency reads that value; if
#   present, the request is blocked with 403.
#
# R49 -- DEPENDENCY LAYER, NOT DECORATOR:
#   The original implementation was a function decorator applied to a
#   single endpoint (sign_document, 1 of 9 restricted operations). It
#   is now a FastAPI dependency factory applied at the route level:
#
#     @router.post("", dependencies=[Depends(forbid_avatar("create_withdrawal"))])
#
#   The inner dependency declares Depends(get_current_user_write) --
#   the same dependency every guarded (mutating) endpoint already
#   uses -- which guarantees two things at zero cost:
#     1. ORDERING: the user (and thus the avatar contextvars) is loaded
#        BEFORE the check runs -- no reliance on parameter order;
#     2. CACHING: FastAPI caches Depends within a request, so the user
#        is loaded exactly once -- no extra Redis or DB round-trip.
#
# GUARDED OPERATIONS (R49 + R50): sign_document (documents/router.py),
#   create_withdrawal (withdrawals/router.py), create_payment
#   (payments/router.py -- BOTH invoice creation and TXID submission
#   since H7: claiming a transfer finishes a deposit somebody else
#   started, so guarding only the first half would leave the second
#   open), create_installment
#   (installments/router.py), create_purchase (purchases/router.py --
#   R50 boss decision: spending the user's balance is exactly the
#   threat class this guard exists for; reversibility via R-2.2 is
#   cleanup, not prevention), modify_kyc (kyc/router.py /submit;
#   /advance intentionally NOT guarded -- it is an idempotent
#   onboarding unstick helper, and blocking it would prevent staff
#   from legitimately unsticking users via avatar; boss decision,
#   see R-2.2 session report Open Notes), logout_all (auth/router.py
#   /logout-all -- STAGE-III-FINDINGS.md #19: unguarded, this route let
#   an avatar end every session the REAL owner holds on every device
#   while its own avatar session survives, a disruption vector with no
#   legitimate avatar-mode use case. /logout does NOT need this: it
#   only ever deletes the caller's own current session, which under
#   avatar mode is the avatar's token -- it just ends the impersonation
#   and touches nothing of the target's).
#
#   The set is SELF-CHECKING: test_avatar.py walks app.routes and
#   asserts every operation above carries its forbid_avatar_*
#   dependency -- removing a guard from a route fails the suite.
#   change_email and delete_account (TASK-38) now have live endpoints
#   too -- POST /api/v1/users/me/email-change (request step only, see
#   users/router.py header) and POST /api/v1/users/me/deactivate
#   (users/router.py). The remaining RESTRICTED_OPERATIONS entries
#   still have no live endpoints (change_password / access_staff_shell)
#   -- apply forbid_avatar when they appear.
#
#   revoke_session (auth/router.py DELETE /sessions/{session_id},
#   TASK-38): same disruption-vector reasoning as logout_all, at
#   single-device granularity -- an avatar session is NOT added to the
#   target user's own user_sessions:{user_id} ZSET (avatar_service.py),
#   so GET /sessions run by an avatar lists only the REAL owner's
#   sessions, on devices the avatar has no legitimate reason to end.
#   GET /sessions itself is left UNGUARDED: it is read-only visibility,
#   the same category of access avatar mode already grants over the
#   target's other data (KYC, financials, etc.) elsewhere in this
#   codebase -- only the destructive half is restricted.
# =============================================================================

from typing import Callable

import structlog
from fastapi import Depends

from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.modules.auth.dependencies import get_current_user_write
from app.modules.users.models import User

# Operations that Staff cannot perform while avataring.
# Defined here as the single source of truth.
RESTRICTED_OPERATIONS = frozenset({
    "change_password",
    "change_email",
    "delete_account",
    "create_payment",
    "create_withdrawal",
    "sign_document",
    "create_installment",
    "create_purchase",
    "access_staff_shell",
    "modify_kyc",
    "logout_all",
    "revoke_session",
})


def _get_avatar_session_id() -> str | None:
    """Read avatar_session_id from structlog contextvars.

    Returns None if not in avatar mode (normal request).
    Returns the session ID string if Staff is avataring.
    """
    ctx = structlog.contextvars.get_contextvars()
    return ctx.get("avatar_session_id")


def forbid_avatar(operation: str) -> Callable:
    """Factory: FastAPI dependency that blocks the operation in avatar mode.

    Apply at the route level so endpoint signatures stay clean:

        @router.post(
            "",
            dependencies=[Depends(forbid_avatar("create_withdrawal"))],
        )

    The dependency loads the current user via get_current_user_write
    (cached by FastAPI -- the endpoint's own user Depends reuses it),
    which guarantees the avatar contextvars are bound before the check.

    Args:
        operation: Name of the operation (must be in RESTRICTED_OPERATIONS).

    Raises:
        ForbiddenError: If avatar_session_id is present in contextvars.
        ValueError: At import time if operation is unknown (dev guard).
    """
    if operation not in RESTRICTED_OPERATIONS:
        raise ValueError(
            f"Unknown restricted operation: '{operation}'. "
            f"Must be one of: {sorted(RESTRICTED_OPERATIONS)}"
        )

    async def _dependency(
        user: User = Depends(get_current_user_write),
    ) -> None:
        # Owner-ruled 2026-08-17: the whole restriction set is OFF by
        # default. Read at request time, not at import time, so the switch
        # can be flipped without a redeploy and so tests can drive it.
        if not settings.avatar_restrictions_enabled:
            return
        if _get_avatar_session_id() is not None:
            raise ForbiddenError(
                f"Operation '{operation}' is not allowed in avatar mode"
            )

    # Meaningful name for FastAPI's dependency resolution / OpenAPI.
    _dependency.__name__ = f"forbid_avatar_{operation}"
    _dependency.__qualname__ = f"forbid_avatar.<locals>.forbid_avatar_{operation}"

    return _dependency
