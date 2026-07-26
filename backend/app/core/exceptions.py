# =============================================================================
# AIVIS.ONE Backend -- Application Exceptions
# =============================================================================
#
# HIERARCHY:
#   AivisError (base)
#   ├── UnauthorizedError        -> 401
#   ├── ForbiddenError           -> 403
#   ├── NotFoundError            -> 404
#   ├── ConflictError            -> 409
#   ├── BadRequestError          -> 400
#   │   └── InsufficientBalanceError -> 400 (Sprint 6.2)
#   ├── RateLimitError           -> 429 (iter 2.5-finishing)
#   └── AMLViolationError        -> 403
#
# USAGE:
#   from app.core.exceptions import NotFoundError
#   raise NotFoundError("Company not found", code="company_not_found")
#
# FastAPI exception handler in main.py converts AivisError -> JSON response:
#   {"error": "<code>", "message": "<message>"}
# =============================================================================


class AivisError(Exception):
    """Base exception for all AIVIS.ONE application errors.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code for API consumers.
        status_code: HTTP status code for the response.
    """

    def __init__(
        self,
        message: str = "An error occurred",
        code: str = "internal_error",
        status_code: int = 500,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class UnauthorizedError(AivisError):
    """Authentication required or token invalid (HTTP 401)."""

    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "unauthorized",
    ) -> None:
        super().__init__(message=message, code=code, status_code=401)


class ForbiddenError(AivisError):
    """Action not allowed for this user (HTTP 403)."""

    def __init__(
        self,
        message: str = "Action not allowed",
        code: str = "forbidden",
    ) -> None:
        super().__init__(message=message, code=code, status_code=403)


class NotFoundError(AivisError):
    """Resource not found (HTTP 404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "not_found",
    ) -> None:
        super().__init__(message=message, code=code, status_code=404)


class ConflictError(AivisError):
    """Action conflicts with current state (HTTP 409).

    Examples: duplicate purchase, concurrent plan creation.
    """

    def __init__(
        self,
        message: str = "Conflict with current state",
        code: str = "conflict",
    ) -> None:
        super().__init__(message=message, code=code, status_code=409)


class BadRequestError(AivisError):
    """Invalid request beyond Pydantic validation (HTTP 400).

    Examples: buying a hidden product, insufficient balance.
    """

    def __init__(
        self,
        message: str = "Bad request",
        code: str = "bad_request",
    ) -> None:
        super().__init__(message=message, code=code, status_code=400)


class InsufficientBalanceError(BadRequestError):
    """Investor balance too low for the requested operation (HTTP 400).

    Subclass of BadRequestError so existing catch-all handlers still work.
    Carries available/required amounts for structured error handling.

    Sprint 6.2: introduced to replace string-matching on error messages
    in installment tranche payment flow.
    """

    def __init__(self, available: int, required: int) -> None:
        self.available = available
        self.required = required
        super().__init__(
            message=(
                f"Insufficient balance: {available} cents available, "
                f"{required} cents required"
            ),
            code="insufficient_balance",
        )


class RateLimitError(AivisError):
    """Rate limit exceeded (HTTP 429 Too Many Requests).

    iter 2.5-finishing: previously check_rate_limit() raised
    BadRequestError -> HTTP 400, which is semantically wrong. Clients
    (frontend, monitoring) cannot distinguish "your request is malformed"
    from "you sent too many requests" without parsing the message.
    429 is the canonical HTTP status; Retry-After lets the client back
    off intelligently rather than hammering the endpoint.

    NOT a subclass of BadRequestError -- callers that catch
    BadRequestError to wrap rate-limit hits into a different exception
    (see auth/telegram.py history) should now let the 429 propagate
    untouched so the global AivisError handler in main.py can emit the
    Retry-After header.

    Attributes:
        retry_after_seconds: Seconds until the rate-limit window resets.
            Surfaced as the standard HTTP `Retry-After` response header
            by the global exception handler. None when the helper could
            not determine TTL (Redis TTL miss -- unlikely but defensive).
    """

    def __init__(
        self,
        message: str = "Too many requests. Please try again later.",
        code: str = "rate_limit_exceeded",
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=429)
        self.retry_after_seconds = retry_after_seconds


class AMLViolationError(AivisError):
    """AML matrix violation -- Active -> Passive ledger route forbidden (HTTP 403).

    Raised by ledger service when a transfer would violate
    the AML route matrix defined in AIVIS-Financial-System.md.
    """

    def __init__(
        self,
        message: str = "Transfer route is not permitted by AML policy",
        code: str = "aml_violation",
    ) -> None:
        super().__init__(message=message, code=code, status_code=403)
