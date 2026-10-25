"""The browser's CORS preflight lets every header the frontend sends through.

The API lives on its own api. host, so every call the frontend makes
with a header beyond the CORS-safelisted ones is preceded by
`OPTIONS` + `Access-Control-Request-Headers`. A header missing from the
server's list is a 400 preflight, and the real request never leaves the
browser -- which no ordinary test sees, because the test client is not a
browser and never sends a preflight. That is how every support message
from a browser died from H23 (`Idempotency-Key`) until this file.

The configuration is read from the app's own CORSMiddleware entry
(`app.user_middleware`), not copied, and driven in both forms the
middleware takes:

  * `*` without credentials -- the development and test default;
  * an explicit origin list with credentials -- every real box
    (production refuses `*`, core/config.py). Starlette takes different
    branches for the two, so the box form is checked on its own;

plus the live app as this environment configured it.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

from app.main import app

FRONTEND_REQUEST_HEADERS = (
    "Authorization",
    "Content-Type",
    "Accept-Language",
    "Idempotency-Key",
)
"""Every request header the frontend sends, from a search of
frontend/src for every way a header is set (the JSON client, each raw
fetch() in src/api/, the referral beacon in the router; there is no
XMLHttpRequest, axios, Headers object, EventSource or WebSocket).
A new header in the frontend needs its line here and in
main.CORS_ALLOW_HEADERS."""

BOX_ORIGIN = "https://app.example.com"
FOREIGN_ORIGIN = "https://evil.example.net"
# The middleware answers a preflight before routing and never looks at
# the path; any path is the same answer.
PREFLIGHT_PATH = "/api/v1/any"


def _cors_kwargs() -> dict[str, Any]:
    entries = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert len(entries) == 1, "the app registers exactly one CORSMiddleware"
    return dict(entries[0].kwargs)


async def _ok(scope: Any, receive: Any, send: Any) -> None:
    await PlainTextResponse("ok")(scope, receive, send)


def _rebuilt(*, origins: list[str], credentials: bool) -> CORSMiddleware:
    kwargs = _cors_kwargs()
    kwargs.update(allow_origins=origins, allow_credentials=credentials)
    return CORSMiddleware(_ok, **kwargs)


def _live_origin() -> str:
    origins = list(_cors_kwargs()["allow_origins"])
    return BOX_ORIGIN if origins == ["*"] else origins[0]


# (name, the ASGI app to drive, an origin it allows)
MODES: dict[str, tuple[Callable[[], Any], Callable[[], str]]] = {
    "box": (
        lambda: _rebuilt(origins=[BOX_ORIGIN], credentials=True),
        lambda: BOX_ORIGIN,
    ),
    "wildcard": (
        lambda: _rebuilt(origins=["*"], credentials=False),
        lambda: BOX_ORIGIN,
    ),
    "live": (lambda: app, _live_origin),
}


@pytest.fixture(params=list(MODES))
async def mode(
    request: pytest.FixtureRequest,
) -> AsyncIterator[tuple[AsyncClient, str, str]]:
    build, origin = MODES[request.param]
    async with AsyncClient(
        transport=ASGITransport(app=build()), base_url="http://test",
    ) as http:
        yield http, origin(), request.param


async def _preflight(
    http: AsyncClient, origin: str, headers: str | None, method: str = "POST",
) -> Any:
    request_headers = {"Origin": origin, "Access-Control-Request-Method": method}
    if headers is not None:
        request_headers["Access-Control-Request-Headers"] = headers
    return await http.options(PREFLIGHT_PATH, headers=request_headers)


def test_every_frontend_header_is_configured() -> None:
    """The list the app passes is not empty and names every header the
    frontend sends -- the pair to the preflights below, which would pass
    vacuously against a middleware that lets everything through."""
    configured = {h.lower() for h in _cors_kwargs()["allow_headers"]}
    assert configured, "allow_headers is empty"
    assert "*" not in configured, "the preflight check below would be vacuous"
    missing = {h.lower() for h in FRONTEND_REQUEST_HEADERS} - configured
    assert not missing, f"not allowed by CORS: {sorted(missing)}"


@pytest.mark.parametrize("header", FRONTEND_REQUEST_HEADERS)
async def test_preflight_admits_each_frontend_header(mode, header: str) -> None:
    """Each header alone, from an allowed origin: 200, and the answer
    names it. `Idempotency-Key` is the one that failed on the box;
    `Accept-Language` passes on Starlette's own safelist as well, and
    this guards against Starlette changing that."""
    http, origin, _ = mode
    response = await _preflight(http, origin, header)
    assert response.status_code == 200, response.text
    allowed = response.headers["access-control-allow-headers"].lower()
    assert header.lower() in [h.strip() for h in allowed.split(",")]


async def test_preflight_admits_the_support_message_set(mode) -> None:
    """What a browser asks before a support message: every header at
    once, in lower case as browsers send them."""
    http, origin, _ = mode
    names = ",".join(h.lower() for h in FRONTEND_REQUEST_HEADERS)
    assert (await _preflight(http, origin, names)).status_code == 200


async def test_preflight_ignores_case_spaces_and_repeats(mode) -> None:
    http, origin, _ = mode
    response = await _preflight(
        http, origin, "Idempotency-Key , ACCEPT-LANGUAGE,idempotency-key",
    )
    assert response.status_code == 200, response.text


async def test_preflight_without_request_headers(mode) -> None:
    """No header named at all: the bare preflight answers 200 -- the
    control that a 400 below comes from the header check, not from the
    preflight itself."""
    http, origin, _ = mode
    assert (await _preflight(http, origin, None)).status_code == 200


@pytest.mark.parametrize(
    "headers", ["X-Not-Allowed", "idempotency-key, x-not-allowed, accept-language"],
)
async def test_preflight_refuses_an_unknown_header(mode, headers: str) -> None:
    """The check works: a header nobody listed is a 400, alone or among
    allowed ones -- one stranger is enough."""
    http, origin, _ = mode
    response = await _preflight(http, origin, headers)
    assert response.status_code == 400
    assert "headers" in response.text.lower()


async def test_box_preflight_refuses_a_foreign_origin() -> None:
    """The box form checks the origin too: the frontend's own headers
    from an origin not in the list are a 400. (The wildcard form admits
    every origin by definition, so this is the box form only.)"""
    middleware = _rebuilt(origins=[BOX_ORIGIN], credentials=True)
    async with AsyncClient(
        transport=ASGITransport(app=middleware), base_url="http://test",
    ) as http:
        response = await _preflight(http, FOREIGN_ORIGIN, "idempotency-key")
    assert response.status_code == 400
    assert "origin" in response.text.lower()
