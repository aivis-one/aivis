# =============================================================================
# CBSHOME Backend -- Avatar Guard (Sprint 1.3)
# =============================================================================
#
# Decorator that blocks certain operations when Staff is in avatar mode
# (logged in as another user via Sprint 3.2 avataring).
#
# HOW IT WORKS:
#   TraceIdMiddleware (Sprint 3.2) will bind avatar_session_id to
#   structlog contextvars when the Redis session contains it. This
#   decorator reads that value. If present + operation is restricted,
#   the request is blocked with 403.
#
# UNTIL PHASE 3:
#   avatar_session_id is never bound in contextvars, so the decorator
#   always passes. No functional impact -- pure infrastructure prep.
#
# USAGE:
#   @require_not_avatar("create_payment")
#   async def create_payment(...):
#       ...
# =============================================================================

from functools import wraps
from typing import Any, Callable

import structlog

from app.core.exceptions import ForbiddenError

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


def require_not_avatar(operation: str) -> Callable:
    """Decorator that blocks the operation in avatar mode.

    Args:
        operation: Name of the operation (must be in RESTRICTED_OPERATIONS).

    Raises:
        ForbiddenError: If avatar_session_id is present in contextvars
            and the operation is restricted.
        ValueError: If operation is not in RESTRICTED_OPERATIONS (dev guard).
    """
    if operation not in RESTRICTED_OPERATIONS:
        raise ValueError(
            f"Unknown restricted operation: '{operation}'. "
            f"Must be one of: {sorted(RESTRICTED_OPERATIONS)}"
        )

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            avatar_id = _get_avatar_session_id()
            if avatar_id is not None:
                raise ForbiddenError(
                    f"Operation '{operation}' is not allowed in avatar mode"
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator
