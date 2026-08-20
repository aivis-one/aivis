# =============================================================================
# AIVIS.ONE Backend -- Comms client: the recipient must exist first (T-64)
# =============================================================================
#
# THE PROBLEM THIS SOLVES. comms delivers to KNOWN recipients only:
# Recipient.id is this product's user id. A notification aimed at a user
# comms has not heard of resolves to an empty audience, the notification
# is marked SKIPPED (terminal, no delivery row, no retry anywhere), and
# the message is gone -- silently. The outbox relay (T-63) syncs
# identities eventually, but "eventually" is exactly what a verification
# message emitted seconds after registration cannot wait for.
#
# So: when a user is created, comms is called SYNCHRONOUSLY and the
# recipient exists before anything is sent.
#
# WHAT THIS MODULE PROMISES, AND WHAT IT REFUSES TO PROMISE.
#   - It never raises. Registration must not become more fragile than it
#     is today: sending the verification e-mail already fails quietly, and
#     a comms outage must not cost a user their account.
#   - It does not retry. One attempt, one short timeout. The retry lives
#     in the outbox instead, where it survives restarts -- retrying here
#     would only make a registering user wait longer for the same answer.
#   - With no COMMS_API_URL configured it does nothing at all and says so
#     once. A box without a comms stack is a supported configuration.
#
# WHERE THE FALLBACK LIVES: not here. The caller (see
# modules/auth/service.py) emits a user_upserted outbox event in the SAME
# transaction when this returns False, so a failed synchronous call
# degrades to the asynchronous path instead of losing the recipient.
#
# TWO POLICIES OVER ONE DOOR (T-65)
# ---------------------------------
# The support module needs to talk to comms too, and it needs the
# OPPOSITE failure policy: a person who pressed "send" is owed an answer,
# so its calls must fail loudly. That is a difference of POLICY, not of
# transport -- there is still exactly one function in this product that
# opens a connection to comms (_call), and it owns the address, the
# service token and the timeout so that nobody can quietly pick a second
# set.
#
#   _call             -- the door. Never raises, never decides.
#   upsert_recipient  -- policy A: every failure is False (see above).
#   comms_request     -- policy B: every failure is a typed AivisError,
#                        which main.py's handler turns into a clean JSON
#                        refusal. "Does not raise" is not the promise
#                        here; "does not leak an unhandled transport
#                        exception" is.
#
# Both policies are deliberate and neither is the default: a second
# caller must pick one on purpose, not inherit one by accident.
# =============================================================================

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import AivisError

if TYPE_CHECKING:  # pragma: no cover -- annotation only
    # Imported for typing only: core must not depend on a product
    # module at runtime, but the snapshot below reads five specific
    # User attributes and typing them is the point of this function.
    from app.modules.users.models import User

logger = structlog.get_logger()

# The comms route this module speaks to (PUT /api/v1/recipients/{id}).
_RECIPIENTS_PATH = "/api/v1/recipients"

# Why the wire produced no answer. Distinguished because the two
# policies below report them differently, and because "this box has no
# comms at all" is a supported configuration, not a fault.
_FAILURE_NOT_CONFIGURED = "not_configured"
_FAILURE_TIMEOUT = "timeout"
_FAILURE_TRANSPORT = "transport"

# The only comms 4xx statuses that say something about THIS request
# rather than about our own configuration. A 401 or a 403 from comms
# means our service token is wrong, and a 405 means our path is -- both
# are infrastructure faults, mapped to 502 rather than forwarded, so a
# misconfigured deployment cannot masquerade as the caller's mistake.
_FORWARDABLE_4XX = frozenset({400, 404, 409, 422})

# How much of comms' own refusal text reaches the log. Bounded because
# it is somebody else's string arriving over the network.
_DETAIL_LOG_LIMIT = 200


class CommsUnavailableError(AivisError):
    """comms could not answer this request (HTTP 502).

    Raised by comms_request only. The recipient upsert has no use for
    it -- see the module header on the two policies.
    """

    def __init__(
        self,
        message: str = "Support service is unavailable",
        code: str = "comms_unavailable",
        status_code: int = 502,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)


class CommsTimeoutError(CommsUnavailableError):
    """comms did not answer within the timeout (HTTP 504).

    A SUBCLASS of CommsUnavailableError, deliberately: a caller that
    only cares whether an answer arrived catches one name and gets
    both, exactly as InsufficientBalanceError subclasses
    BadRequestError in this tree. A caller that wants to tell "slow"
    from "down" apart still can.
    """

    def __init__(
        self,
        message: str = "Support service timed out",
        code: str = "comms_timeout",
    ) -> None:
        super().__init__(message=message, code=code, status_code=504)


class CommsRejectedError(AivisError):
    """comms refused this request with a status it models (HTTP 4xx).

    Carries comms' STATUS but not comms' WORDING. Its messages name
    internal objects ("client recipient <uuid> does not exist") and a
    product response is not the place for them; the original text is
    logged instead, where whoever debugs this can read it.
    """

    def __init__(
        self,
        status_code: int,
        message: str = "Support service rejected the request",
        code: str = "comms_rejected",
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)


@dataclass(frozen=True)
class _CallResult:
    """One attempt at the wire: an answer, or the reason there is none."""

    response: httpx.Response | None
    failure: str | None = None
    error: str = ""


def comms_configured() -> bool:
    """True when this box has a comms address to talk to."""
    return bool(settings.comms_api_url)


async def _call(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> _CallResult:
    """THE door: the only place this product opens a socket to comms.

    Owns the address, the service token and the timeout, so a second
    caller cannot quietly choose a different one. Owns NOTHING about
    what a failure means -- that is the policy of the two functions
    below, and they disagree on purpose.

    Never raises. It cannot: one of the two policies over it promises
    never to raise either, and a door that threw would make that
    promise impossible to keep without a catch-all somebody will
    eventually widen.
    """
    if not comms_configured():
        return _CallResult(response=None, failure=_FAILURE_NOT_CONFIGURED)

    url = f"{settings.comms_api_url.rstrip('/')}{path}"
    headers = {"Authorization": f"Bearer {settings.comms_service_token}"}

    try:
        async with httpx.AsyncClient(
            timeout=settings.comms_http_timeout_seconds
        ) as client:
            response = await client.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        # Checked before HTTPError: TimeoutException is one of its
        # subclasses, and the order is what keeps them distinguishable.
        return _CallResult(None, _FAILURE_TIMEOUT, str(exc))
    except httpx.HTTPError as exc:
        # ConnectError, DNS, protocol errors -- the pipe, not the
        # request.
        return _CallResult(None, _FAILURE_TRANSPORT, str(exc))

    return _CallResult(response=response)


def _refusal_detail(response: httpx.Response) -> str:
    """comms' own words for a refusal -- FOR THE LOG ONLY.

    Never returned to a caller and never rendered into a response body:
    see CommsRejectedError on why comms' wording stays inside.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:_DETAIL_LOG_LIMIT]
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail[:_DETAIL_LOG_LIMIT]
    return ""


def user_snapshot(user: "User") -> dict[str, Any]:
    """Build the identity snapshot comms stores for one user.

    A SNAPSHOT, not a patch: every field is always present and "no
    value" is an explicit None. comms overwrites what it holds with
    exactly this, so omitting a field would mean "keep the old value" --
    a semantic this contract does not have.

    timezone is always None: this product does not track a user
    timezone at all, and comms falls back to its own default when
    computing quiet hours. It is passed anyway, and explicitly, because
    the absence of the key is a different thing from the value None.
    """
    credentials = user.credentials or {}
    telegram = credentials.get("telegram") or {}
    telegram_id = telegram.get("id")
    return {
        "telegram_id": int(telegram_id) if telegram_id is not None else None,
        "email": user.email,
        "locale": user.language,
        "timezone": None,
        "active": user.is_active,
    }


async def upsert_recipient(recipient_id: UUID, snapshot: dict[str, Any]) -> bool:
    """Create or update the recipient in comms. Returns success.

    Never raises: every failure -- unconfigured, unreachable, refused,
    rejected -- is logged and reported as False, so the caller decides
    what to do about it. The caller is expected to fall back to the
    outbox rather than to fail the operation that triggered this.
    """
    result = await _call(
        "PUT", f"{_RECIPIENTS_PATH}/{recipient_id}", json=snapshot
    )

    if result.failure == _FAILURE_NOT_CONFIGURED:
        # Not an error and not once per user: a box without comms says
        # this on every registration, which is why it is INFO with the
        # user id and not a warning.
        logger.info(
            "comms_upsert_skipped_no_url",
            recipient_id=str(recipient_id),
        )
        return False

    if result.failure == _FAILURE_TIMEOUT:
        logger.warning(
            "comms_upsert_timeout",
            recipient_id=str(recipient_id),
            error=result.error,
        )
        return False

    response = result.response
    if response is None:
        logger.warning(
            "comms_upsert_request_failed",
            recipient_id=str(recipient_id),
            error=result.error,
        )
        return False

    if response.status_code in (401, 403):
        # Configuration, not weather: a wrong or empty service token
        # fails every call the same way and will not heal on its own.
        logger.error(
            "comms_upsert_unauthorized",
            recipient_id=str(recipient_id),
            status=response.status_code,
        )
        return False

    if response.status_code >= 400:
        logger.warning(
            "comms_upsert_rejected",
            recipient_id=str(recipient_id),
            status=response.status_code,
        )
        return False

    logger.info("comms_recipient_upserted", recipient_id=str(recipient_id))
    return True


async def comms_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    """One request to comms on a path a PERSON is waiting on.

    The opposite policy to upsert_recipient's, over the same door. A
    user who pressed "send" is owed the outcome, so nothing here is
    swallowed: every failure becomes a typed AivisError that main.py's
    handler renders as {"error", "message"} with a real status. What
    must NOT happen is an httpx exception escaping into the request --
    that is a 500 and tells the user nothing.

    There is no outbox fallback and cannot be one: the relay carries
    the four envelope types in core/events/service.py, none of which is
    "put this message in a thread", and comms has no consumer for such
    an event. Retrying later is also the wrong promise for a message a
    person is watching the screen for.

    Args:
        method: HTTP method ("GET", "POST").
        path: comms API path starting with "/".
        params: optional query parameters.
        json: optional JSON body.

    Returns:
        The response body, parsed as JSON.

    Raises:
        CommsTimeoutError: comms did not answer in time (504).
        CommsUnavailableError: unreachable, unconfigured, upstream 5xx,
            an auth fault of OUR service token, an unmodeled 4xx, or a
            body that is not JSON (502).
        CommsRejectedError: comms answered with a status it models --
            400 / 404 / 409 / 422 -- forwarded as that status.
    """
    result = await _call(method, path, params=params, json=json)

    if result.failure == _FAILURE_NOT_CONFIGURED:
        # A box without comms is a supported configuration for the
        # recipient upsert, which has an outbox behind it. It is NOT a
        # supported configuration for a support conversation: there is
        # nowhere for the message to go, and saying so is the only
        # honest answer.
        logger.warning("comms_request_not_configured", path=path)
        raise CommsUnavailableError()

    if result.failure == _FAILURE_TIMEOUT:
        logger.warning(
            "comms_request_timeout", path=path, error=result.error
        )
        raise CommsTimeoutError()

    response = result.response
    if response is None:
        logger.warning(
            "comms_request_failed", path=path, error=result.error
        )
        raise CommsUnavailableError()

    status = response.status_code

    if status >= 500:
        logger.warning("comms_upstream_error", path=path, status=status)
        raise CommsUnavailableError()

    if status in (401, 403):
        # OUR service token, never this user's session. Forwarding the
        # status verbatim would be read by the frontend as "your
        # session expired" and log out everyone who opened support
        # while the token was wrong.
        logger.error("comms_auth_error", path=path, status=status)
        raise CommsUnavailableError()

    if status >= 400:
        detail = _refusal_detail(response)
        if status not in _FORWARDABLE_4XX:
            logger.warning(
                "comms_unexpected_4xx",
                path=path,
                status=status,
                detail=detail,
            )
            raise CommsUnavailableError()
        logger.info(
            "comms_rejected", path=path, status=status, detail=detail
        )
        raise CommsRejectedError(status_code=status)

    try:
        return response.json()
    except ValueError:
        # A 200 that is not JSON is comms answering something other
        # than its own API -- a proxy error page, most likely. It is an
        # upstream fault, not an empty result.
        logger.warning("comms_response_not_json", path=path)
        raise CommsUnavailableError() from None
