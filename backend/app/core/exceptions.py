# =============================================================================
# CBSHOME Backend -- Application Exceptions
# =============================================================================
#
# HIERARCHY:
#   CBSError (base)
#   ├── UnauthorizedError        -> 401
#   ├── ForbiddenError           -> 403
#   ├── NotFoundError            -> 404
#   ├── ConflictError            -> 409
#   ├── BadRequestError          -> 400
#   │   └── InsufficientBalanceError -> 400 (Sprint 6.2)
#   └── AMLViolationError        -> 403
#
# USAGE:
#   from app.core.exceptions import NotFoundError
#   raise NotFoundError("Company not found", code="company_not_found")
#
# FastAPI exception handler in main.py converts CBSError -> JSON response:
#   {"error": "<code>", "message": "<message>"}
# =============================================================================


class CBSError(Exception):
    """Base exception for all CBSHOME application errors.

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


class UnauthorizedError(CBSError):
    """Authentication required or token invalid (HTTP 401)."""

    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "unauthorized",
    ) -> None:
        super().__init__(message=message, code=code, status_code=401)


class ForbiddenError(CBSError):
    """Action not allowed for this user (HTTP 403)."""

    def __init__(
        self,
        message: str = "Action not allowed",
        code: str = "forbidden",
    ) -> None:
        super().__init__(message=message, code=code, status_code=403)


class NotFoundError(CBSError):
    """Resource not found (HTTP 404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "not_found",
    ) -> None:
        super().__init__(message=message, code=code, status_code=404)


class ConflictError(CBSError):
    """Action conflicts with current state (HTTP 409).

    Examples: duplicate purchase, concurrent plan creation.
    """

    def __init__(
        self,
        message: str = "Conflict with current state",
        code: str = "conflict",
    ) -> None:
        super().__init__(message=message, code=code, status_code=409)


class BadRequestError(CBSError):
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


class AMLViolationError(CBSError):
    """AML matrix violation -- Active -> Passive ledger route forbidden (HTTP 403).

    Raised by ledger service when a transfer would violate
    the AML route matrix defined in CBSHOME-Financial-System.md.
    """

    def __init__(
        self,
        message: str = "Transfer route is not permitted by AML policy",
        code: str = "aml_violation",
    ) -> None:
        super().__init__(message=message, code=code, status_code=403)
