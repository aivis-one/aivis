# =============================================================================
# CBSHOME Backend -- Avatar Guard (Sprint 1.3, dependency-layer R49)
# =============================================================================
#
# Blocks certain operations when Staff is in avatar mode (logged in as
# another user via Sprint 3.2 avataring).
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
#   (payments/router.py crypto-address), create_installment
#   (installments/router.py), create_purchase (purchases/router.py --
#   R50 boss decision: spending the user's balance is exactly the
#   threat class this guard exists for; reversibility via R-2.2 is
#   cleanup, not prevention), modify_kyc (kyc/router.py /submit;
#   /advance intentionally NOT guarded -- it is an idempotent
#   onboarding unstick helper, and blocking it would prevent staff
#   from legitimately unsticking users via avatar; boss decision,
#   see R-2.2 session report Open Notes).
#
#   The set is SELF-CHECKING: test_avatar.py walks app.routes and
#   asserts every operation above carries its forbid_avatar_*
#   dependency -- removing a guard from a route fails the suite.
#   The remaining RESTRICTED_OPERATIONS entries have no live endpoints
#   yet (change_password / change_email / delete_account /
#   access_staff_shell) -- apply forbid_avatar when they appear.
# =============================================================================

from typing import Callable

import structlog
from fastapi import Depends

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
        if _get_avatar_session_id() is not None:
            raise ForbiddenError(
                f"Operation '{operation}' is not allowed in avatar mode"
            )

    # Meaningful name for FastAPI's dependency resolution / OpenAPI.
    _dependency.__name__ = f"forbid_avatar_{operation}"
    _dependency.__qualname__ = f"forbid_avatar.<locals>.forbid_avatar_{operation}"

    return _dependency
