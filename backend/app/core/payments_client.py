# =============================================================================
# AIVIS.ONE Backend -- Payments service client (H7)
# =============================================================================
#
# THE PRODUCT IS A CLIENT OF THE PAYMENTS SERVICE, NOT ITS PEER. Whatever
# the service does not do, this product does not do either, and anything
# the product would otherwise have to derive from the service's internal
# thresholds the service hands over itself (TOR section 11 p.12). That
# principle is why this module contains no invoice logic at all: no
# status machine, no attempt budget, no network list. It moves three
# calls across a socket and turns their outcomes into types.
#
# WHY THIS LOOKS LIKE core/comms.py. It is deliberately the same shape:
# one function owns the address, the token and the timeout, and the
# policy sits above it. A second place that opens a socket to payments
# is a second place that can quietly pick a different timeout.
#
# ONE POLICY, AND IT IS THE LOUD ONE. comms needs two because a
# notification may be dropped and a support message may not. Every call
# here is behind a button a person just pressed, so there is nobody to
# degrade for: every failure becomes a typed AivisError that main.py's
# handler renders as a clean refusal. Silence would leave a user staring
# at a spinner in front of a payment.
#
# NOT CONFIGURED IS NOT AN ERROR SHAPE OF ITS OWN. A box with no
# PAYMENTS_API_URL is a supported configuration -- and, until the deploy
# hand-over of TOR section 9 exists, it is the ONLY configuration -- so
# it answers the same 503 as an unreachable service rather than a 500.
# The user-facing text for both is "temporarily unavailable", because
# both are true statements about the deployment and neither is something
# the user did.
# =============================================================================

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import AivisError

logger = structlog.get_logger()

_INVOICES_PATH = "/api/v1/invoices"

# Why the wire produced no answer.
_FAILURE_NOT_CONFIGURED = "not_configured"
_FAILURE_TIMEOUT = "timeout"
_FAILURE_TRANSPORT = "transport"

# How much of the service's own refusal text reaches the log. Bounded
# because it is somebody else's string arriving over the network.
_DETAIL_LOG_LIMIT = 200


class PaymentsUnavailableError(AivisError):
    """The payments service could not answer this request (HTTP 503).

    Covers the unreachable service and the unconfigured one alike: see
    the module header on why those are one answer and not two.
    """

    def __init__(
        self,
        message: str = "Payments service is unavailable",
        code: str = "payments_unavailable",
        status_code: int = 503,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)


class PaymentsTimeoutError(PaymentsUnavailableError):
    """The payments service did not answer within the timeout (HTTP 504).

    A SUBCLASS of PaymentsUnavailableError, following CommsTimeoutError:
    a caller that only cares whether an answer arrived catches one name
    and gets both, while a caller that must tell "slow" from "down"
    still can.

    Telling them apart matters exactly once here, and it is not
    cosmetic: a timeout on invoice creation may have left an invoice
    behind in the service, and a refusal to connect cannot have.
    """

    def __init__(
        self,
        message: str = "Payments service timed out",
        code: str = "payments_timeout",
    ) -> None:
        super().__init__(message=message, code=code, status_code=504)


class PaymentsRejectedError(AivisError):
    """The service refused this request with a code it models.

    Carries the service's ERROR CODE, which is a closed vocabulary
    (TOR section 8), and not its prose. The code is what a caller
    branches on; the prose names invoices by uuid and belongs in a log.
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str = "Payments service rejected the request",
    ) -> None:
        super().__init__(
            message=message,
            code="payments_rejected",
            status_code=status_code,
        )
        self.error_code = error_code


class PaymentsMalformedError(AivisError):
    """The service answered, and the answer cannot be used (HTTP 502).

    A 201 with no ``address``, a body that is not an object, a missing
    ``id`` -- all mean the same thing to a caller: there is nothing here
    to show a user. Distinguished from PaymentsUnavailableError only in
    the log, because the fix is different: an unavailable service is
    operations, a malformed answer is a contract break.
    """

    def __init__(
        self,
        message: str = "Payments service returned an unusable response",
        code: str = "payments_malformed",
        status_code: int = 502,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)


@dataclass(frozen=True)
class _CallResult:
    """One attempt at the wire: an answer, or the reason there is none."""

    response: httpx.Response | None
    failure: str | None = None
    error: str = ""


def payments_configured() -> bool:
    """True when this box has a payments service to talk to."""
    return bool(settings.payments_api_url)


async def _call(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> _CallResult:
    """THE door: the only place this product opens a socket to payments.

    Owns the address, the service token and the timeout. Owns NOTHING
    about what a failure means -- that is _answer below.

    Never raises, so that the one place which decides what a failure
    means is the one place that has to be read to know.
    """
    if not payments_configured():
        return _CallResult(response=None, failure=_FAILURE_NOT_CONFIGURED)

    url = f"{settings.payments_api_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {settings.payments_service_token}"}

    try:
        async with httpx.AsyncClient(
            timeout=settings.payments_http_timeout_seconds
        ) as client:
            response = await client.request(method, url, json=json, headers=headers)
    except httpx.TimeoutException as exc:
        # Checked before HTTPError: TimeoutException is one of its
        # subclasses, and the order is what keeps them distinguishable.
        return _CallResult(None, _FAILURE_TIMEOUT, str(exc))
    except httpx.HTTPError as exc:
        return _CallResult(None, _FAILURE_TRANSPORT, str(exc))

    return _CallResult(response=response)


def _error_code(response: httpx.Response) -> str:
    """The service's ``error`` code, or "" when the body has none.

    One envelope covers the whole service API -- ``{"error": "<code>"}``
    for every refusal, with ``detail`` added only on 422 (TOR section 8)
    -- so this reads one key and does not guess at shapes.
    """
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        code = body.get("error")
        if isinstance(code, str):
            return code[:_DETAIL_LOG_LIMIT]
    return ""


def _answer(result: _CallResult, *, operation: str) -> dict[str, Any]:
    """Turn one wire outcome into a body or into a typed refusal.

    Every branch here is reachable and each has been given its own type
    rather than a shared one: the caller of invoice creation has to tell
    a timeout apart from everything else (an invoice may exist over
    there), and the caller of TXID submission has to tell a modelled
    refusal apart from everything else (it must not decrement the
    attempt counter on anything but a real verdict).
    """
    if result.failure == _FAILURE_NOT_CONFIGURED:
        # INFO, not WARNING: a box without a payments stack is a
        # supported configuration and says this on every deposit
        # attempt. See the module header.
        logger.info("payments_call_skipped_no_url", operation=operation)
        raise PaymentsUnavailableError()

    if result.failure == _FAILURE_TIMEOUT:
        logger.warning(
            "payments_call_timeout", operation=operation, error=result.error
        )
        raise PaymentsTimeoutError()

    response = result.response
    if response is None:
        logger.warning(
            "payments_call_transport_failed",
            operation=operation,
            error=result.error,
        )
        raise PaymentsUnavailableError()

    if response.status_code in (401, 403):
        # Configuration, not weather: a wrong or empty service token
        # fails every call identically and will not heal on its own.
        # Never forwarded to the user as an authorisation problem --
        # it is not theirs.
        logger.error(
            "payments_call_unauthorized",
            operation=operation,
            status=response.status_code,
        )
        raise PaymentsUnavailableError()

    if response.status_code >= 500:
        logger.warning(
            "payments_call_upstream_error",
            operation=operation,
            status=response.status_code,
        )
        raise PaymentsUnavailableError()

    if response.status_code >= 400:
        code = _error_code(response)
        logger.warning(
            "payments_call_rejected",
            operation=operation,
            status=response.status_code,
            error_code=code,
        )
        raise PaymentsRejectedError(
            status_code=response.status_code, error_code=code
        )

    try:
        body = response.json()
    except ValueError:
        logger.warning("payments_call_non_json", operation=operation)
        raise PaymentsMalformedError() from None

    if not isinstance(body, dict):
        # A list or a bare string parses fine and is still unusable.
        # Checked because "it was JSON" is not "it was the object we
        # asked for".
        logger.warning("payments_call_not_an_object", operation=operation)
        raise PaymentsMalformedError()

    return body


def _require(body: dict[str, Any], keys: tuple[str, ...], *, operation: str) -> None:
    """Every key present AND non-empty, or the answer is unusable.

    ``in body`` is not the test. A 201 carrying ``address: ""`` or
    ``address: null`` passes a presence check and then puts an empty
    string on a payment screen, which is the same class of defect this
    whole delivery removes: a deposit surface that looks like it works.
    Zero is not treated as empty -- it is a legitimate amount elsewhere
    in this contract -- so the emptiness test is against None and the
    empty string only.
    """
    missing = [k for k in keys if body.get(k) is None or body.get(k) == ""]
    if missing:
        logger.warning(
            "payments_call_incomplete_body", operation=operation, missing=missing
        )
        raise PaymentsMalformedError()


async def create_invoice(
    *,
    product_ref: str,
    network: str,
    invoice_amount_cents: int,
) -> dict[str, Any]:
    """POST /api/v1/invoices -- open an invoice.

    NOT IDEMPOTENT, AND THE SERVICE SAYS SO. Two calls with the same
    product_ref create two invoices: there is no unique index on it
    (TOR section 11 p.11), and closing that gap is service-side work
    (P-23), not something a client can do. What the caller can do is
    not make the second call, which is why the row is written first
    and consulted before this is reached.

    Consequence a caller must handle: on PaymentsTimeoutError an
    invoice may exist over there under this product_ref while we hold
    no id for it. That orphan is harmless rather than dangerous -- the
    deposit address is static per network and the service's partial
    unique index on (network, txid) will not let one transfer settle
    against two invoices -- but it is real, and it is why the caller
    must not retry this call automatically.
    """
    result = await _call(
        "POST",
        _INVOICES_PATH,
        json={
            "product_ref": product_ref,
            "network": network,
            "invoice_amount_cents": invoice_amount_cents,
        },
    )
    body = _answer(result, operation="create_invoice")
    _require(
        body,
        ("id", "network", "address", "status", "expires_at"),
        operation="create_invoice",
    )
    return body


async def get_invoice(invoice_id: UUID) -> dict[str, Any]:
    """GET /api/v1/invoices/{id} -- the service's current view.

    THIS ANSWER OVERTAKES THE EVENT STREAM. An invoice past its TTL
    reads as ``expired`` here while the service's own row still says
    ``created``: expiry is resolved lazily on read and the matching
    event is emitted later by a sweeper (TOR section 8, section 11
    p.7). So a terminal status from this call is true, and the absence
    of a webhook for it means nothing.

    ``address`` is not required of this body. The service returns it,
    but a status poll that failed only because the address was blank
    would take a screen down over a field the screen already has.
    """
    result = await _call("GET", f"{_INVOICES_PATH}/{invoice_id}")
    body = _answer(result, operation="get_invoice")
    _require(body, ("id", "status"), operation="get_invoice")
    return body


async def submit_txid(invoice_id: UUID, txid: str) -> dict[str, Any]:
    """POST /api/v1/invoices/{id}/txid -- hand one TXID to the service.

    A MALFORMED TXID IS A 200 HERE, NOT A 4xx. The service answers 200
    with ``result_code: "invalid_format"`` and, having never reached an
    explorer, spends no attempt (TOR section 8; verified against the
    INVALID_FORMAT / API_ERROR branch of the service's transition
    function, which returns no attempt record and no counter delta).
    A caller that renders a 200 as success, or that decrements a
    counter on one, lies to the user in opposite directions.

    The five refusals -- slot_occupied, attempts_exhausted,
    invoice_already_confirmed, invoice_expired, invoice_stalled -- are
    409s and arrive as PaymentsRejectedError with the code intact.
    """
    result = await _call(
        "POST", f"{_INVOICES_PATH}/{invoice_id}/txid", json={"txid": txid}
    )
    body = _answer(result, operation="submit_txid")
    _require(body, ("status", "result_code"), operation="submit_txid")
    return body
